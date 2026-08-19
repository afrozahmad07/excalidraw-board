#!/usr/bin/env python3
"""Build a multi-panel board from library icons and primitives — no image spend.

    python3 scripts/build.py <spec.json>

The declarative counterpart to `build.py`. That one places generated
images; this one places native elements, so a board costs nothing and renders
identically on every run.

A panel names a `layout` and its content. See `specs/tailscale-acls-native.json`.

Two checks run at build time and both fail the build loudly:

  bounds     — every mark inside its own panel. An earlier hand-placed version
               pushed icons and labels out onto the caption, which is invisible
               at board zoom and therefore shipped.
  collisions — no two pieces of lettering overlapping. Same reason.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from excalidraw_kit import Board, txt, rect, arrow, measure   # noqa: E402
import scene                                                  # noqa: E402

CREAM = "#fdf6e3"
TITLE_C = "#e8590c"
MARGIN = 46


def wrap(text, size, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if measure(t, size)[0] <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return "\n".join(lines)


def check_bounds(elements, x, y, w, h, name):
    bad = [e for e in elements
           if e["x"] < x + MARGIN or e["y"] < y + MARGIN
           or e["x"] + e.get("width", 0) > x + w - MARGIN
           or e["y"] + e.get("height", 0) > y + h - MARGIN]
    for e in bad[:6]:
        print(f"    BOUNDS {name}: {e['id']} at "
              f"({round(e['x'] - x)},{round(e['y'] - y)}) "
              f"size {round(e.get('width', 0))}x{round(e.get('height', 0))}")
    return len(bad)


def check_collisions(elements, name):
    """Lettering must not sit on top of other lettering."""
    texts = [e for e in elements if e.get("type") == "text"]
    hits = 0
    for i, a in enumerate(texts):
        for c in texts[i + 1:]:
            if (a["x"] < c["x"] + c["width"] and c["x"] < a["x"] + a["width"]
                    and a["y"] < c["y"] + c["height"]
                    and c["y"] < a["y"] + a["height"]):
                hits += 1
                if hits <= 4:
                    print(f"    OVERLAP {name}: {a.get('text','')[:22]!r} "
                          f"over {c.get('text','')[:22]!r}")
    return hits


def build(spec):
    b = Board(background=spec.get("background", CREAM))
    pw = spec.get("panel_w", 1180)
    ph = spec.get("panel_h", 780)
    gap = spec.get("gap", 300)
    problems = 0

    for i, p in enumerate(spec["panels"]):
        x, y = 120 + i * (pw + gap), 260
        # Bounds must be set BEFORE anything is drawn for this panel — the title
        # is clamped too, and with a stale value every title drifted one panel
        # left and landed on its neighbour.
        scene.BOUNDS[0] = (x, y, pw, ph)
        start = len(b.elements)
        scene.label(b, p["head"], x + pw / 2, y - 90, 40, TITLE_C)
        b.add(rect(f"frame{i}", x, y, pw, ph, stroke="#d6ccbd",
                   bg=scene.PANEL_BG))

        layout = scene.LAYOUTS.get(p["layout"])
        if not layout:
            sys.exit(f"unknown layout: {p['layout']}")
        layout(b, x, y, pw, ph, p)
        if p.get("footnote"):
            scene.label(b, p["footnote"], x + pw / 2, y + ph - 90, 24,
                        scene.MUTED)

        body = b.elements[start:]
        # The title sits above the frame by design, so bounds-check the panel
        # contents only — but collision-check the title too, since a drifting
        # title landing on its neighbour is exactly the bug this caught.
        problems += check_bounds(body[2:], x, y, pw, ph, p["head"][:24])
        problems += check_collisions(body, p["head"][:24])

        cap = wrap(p["caption"], 22, pw - 60)
        cw, _ = measure(cap, 22)
        e = txt(f"cap{i}", x + (pw - cw) / 2, y + ph + 34, cap, 22, scene.MUTED)
        e["textAlign"] = "center"
        b.add(e)

        if i < len(spec["panels"]) - 1:
            b.add(arrow(f"flow{i}", x + pw + 70, y + ph / 2, gap - 140, 0,
                        color=scene.INK, curved=False))
    return b, problems


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    spec = json.loads(pathlib.Path(sys.argv[1]).read_text())
    b, problems = build(spec)
    out = pathlib.Path(spec["out"])
    if not out.is_absolute():
        # Relative to where the user ran the command, so a board lands in their
        # project rather than inside the skill folder.
        out = pathlib.Path.cwd() / out
    b.save(out)
    print(f"  images: 0   credits: 0   problems: {problems}")
    return problems


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
