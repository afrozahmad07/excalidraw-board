#!/usr/bin/env python3
"""Turn a local .excalidraw file into a clickable excalidraw.com link.

    python3 share_link.py <file.excalidraw>

A file path is not much use — this gives back a URL that opens the board, fully
editable, in any browser.

Why it drives the real Share button instead of the MCP server's
`export_to_excalidraw_url`: that tool uploads the scene JSON but NOT the
embedded image files, so every panel comes back as a broken-image placeholder.
The failure is silent — the link opens, the layout is perfect, and the art is
simply gone. Excalidraw's own Share flow uploads the files too.

Needs the playwright venv; there is no bare `python` on this box and system
python3 cannot import playwright.
"""

import pathlib
import re
import sys
import time

try:
    from playwright.sync_api import sync_playwright
except ImportError:                                   # optional extra
    sys.exit("This step needs Playwright, which the core build does not.\n"
             "  python3 -m pip install playwright && python3 -m playwright "
             "install chromium\n"
             "Everything else in this skill works without it.")

SHARE_BUTTONS = ["button:has-text('Export to link')",
                 "button:has-text('Shareable link')",
                 "button:has-text('Create link')",
                 "[aria-label*='link' i]"]


def share(src, verify=True):
    src = str(pathlib.Path(src).resolve())
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_context(viewport={"width": 1600, "height": 1100}).new_page()
        pg.goto("https://excalidraw.com", wait_until="networkidle", timeout=90000)
        time.sleep(3)
        for sel in ["button:has-text('Close')", "[aria-label='Close']"]:
            try:
                pg.click(sel, timeout=1500)
            except Exception:
                pass

        # Excalidraw takes a .excalidraw payload through a drop event.
        pg.evaluate("""() => {
            const i = document.createElement('input');
            i.type='file'; i.id='__load'; i.style.position='fixed'; i.style.top='0';
            document.body.appendChild(i);
        }""")
        pg.set_input_files("#__load", src)
        pg.evaluate("""() => {
            const i = document.getElementById('__load');
            const dt = new DataTransfer(); dt.items.add(i.files[0]);
            document.querySelector('canvas').dispatchEvent(
              new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true}));
            i.remove();
        }""")
        time.sleep(6)

        pg.click("button:has-text('Share')", timeout=15000)
        time.sleep(2)
        for sel in SHARE_BUTTONS:
            try:
                pg.click(sel, timeout=4000)
                break
            except Exception:
                continue
        time.sleep(12)   # embedded PNGs upload after the scene

        link = None
        try:
            link = pg.input_value("input[readonly]", timeout=8000)
        except Exception:
            m = re.search(r"https://excalidraw\.com/#json=[A-Za-z0-9_\-]+,"
                          r"[A-Za-z0-9_\-]+", pg.content())
            link = m.group(0) if m else None
        b.close()

    if not link:
        print("FAILED: no link returned", file=sys.stderr)
        return None

    if verify and not _renders(link):
        print("WARNING: the link opened but an embedded image did not load.",
              file=sys.stderr)
    return link


def _renders(link):
    """Open the link cold and confirm no resource 404s — the broken-image tell."""
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_context(viewport={"width": 1400, "height": 900}).new_page()
        errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.goto(link, wait_until="networkidle", timeout=90000)
        time.sleep(8)
        b.close()
    return not [e for e in errs if "404" in e]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    url = share(sys.argv[1])
    if not url:
        sys.exit(1)
    print(url)
