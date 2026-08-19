#!/usr/bin/env python3
"""Render a .excalidraw file to a high-resolution PNG you can just open.

    python3 export_png.py <file...>

A .excalidraw file is JSON — double-clicking it opens a text editor, not a
picture. This writes a PNG next to it so the board can be viewed, dropped into a
post, or sent to someone without going near excalidraw.com.

The viewport is sized to the board's own aspect ratio and rendered at 2x, so a
five-panel board comes out sharp rather than letterboxed into 16:9.
"""

import json
import pathlib
import sys
import time

try:
    from playwright.sync_api import sync_playwright
except ImportError:                                   # optional extra
    sys.exit("This step needs Playwright, which the core build does not.\n"
             "  python3 -m pip install playwright && python3 -m playwright "
             "install chromium\n"
             "Everything else in this skill works without it.")

MAX_W = 3400          # keeps a very wide board under control
MIN_W = 1400


def board_aspect(path):
    d = json.loads(pathlib.Path(path).read_text())
    els = [e for e in d.get("elements", []) if not e.get("isDeleted")]
    if not els:
        return 16 / 9
    x1 = min(e["x"] for e in els)
    y1 = min(e["y"] for e in els)
    x2 = max(e["x"] + e.get("width", 0) for e in els)
    y2 = max(e["y"] + e.get("height", 0) for e in els)
    return (x2 - x1) / (y2 - y1) if y2 > y1 else 16 / 9


def export(paths):
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for src in paths:
            src = pathlib.Path(src).resolve()
            aspect = board_aspect(src)
            w = int(min(MAX_W, max(MIN_W, 1100 * aspect)))
            h = int(max(700, w / aspect))
            ctx = b.new_context(viewport={"width": w, "height": h},
                                device_scale_factor=2)
            pg = ctx.new_page()
            pg.goto("https://excalidraw.com", wait_until="networkidle",
                    timeout=90000)
            time.sleep(3)
            for sel in ["button:has-text('Close')", "[aria-label='Close']"]:
                try:
                    pg.click(sel, timeout=1200)
                except Exception:
                    pass
            pg.evaluate("""() => {
                const i = document.createElement('input');
                i.type='file'; i.id='__l'; i.style.position='fixed'; i.style.top='0';
                document.body.appendChild(i);
            }""")
            pg.set_input_files("#__l", str(src))
            pg.evaluate("""() => {
                const i = document.getElementById('__l');
                const dt = new DataTransfer(); dt.items.add(i.files[0]);
                document.querySelector('canvas').dispatchEvent(
                  new DragEvent('drop', {dataTransfer: dt, bubbles: true,
                                         cancelable: true}));
                i.remove();
            }""")
            time.sleep(7)
            pg.keyboard.press("Shift+1")
            time.sleep(3)
            # Hide the editor chrome so the PNG is just the board.
            pg.evaluate("""() => {
                document.querySelectorAll('.App-menu, .App-toolbar-container,'
                  + '.layer-ui__wrapper, .App-bottom-bar, .help-icon')
                  .forEach(e => e.style.display = 'none');
            }""")
            time.sleep(1)
            out = src.with_suffix(".png")
            pg.screenshot(path=str(out))
            print(f"{out}  ({w}x{h} @2x)")
            ctx.close()
        b.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    export(sys.argv[1:])
