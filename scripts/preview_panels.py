#!/usr/bin/env python3
"""Split a spec into one .excalidraw file per panel, so each can be judged.

    python3 scripts/preview_panels.py <spec.json>
    python3 scripts/preview_panels.py <spec.json> --panel 3
    python3 scripts/preview_panels.py <spec.json> --out /tmp/look --png

A fit-to-screen screenshot of a seven-panel board is about 14% zoom. Overlaps,
clipped labels, mis-centred captions and icons a fraction of the size of their
neighbours are all invisible at that scale, and every one of them has shipped.
Opening one panel on its own is the only way to see them.

Each panel is rebuilt through the ordinary build path, so what you look at here
is exactly what the full board contains — same layouts, same auto-fit, same
bounds and collision checks. The difference is that the checks are reported per
panel, so a problem count points at the panel that caused it instead of at the
board as a whole.
"""

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import build as B                                             # noqa: E402

# Copied onto every single-panel spec, so a preview panel is the same size and
# the same colours as it is in the finished board.
# "title" is not carried: build() never reads it.
CARRIED = ("panel_w", "panel_h", "gap", "background", "theme")


def slug(text, limit=32):
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s[:limit].strip("-") or "panel"


def preview(spec_path, out_dir=None, only=None, png=False):
    spec_path = pathlib.Path(spec_path)
    try:
        spec = json.loads(spec_path.read_text())
    except json.JSONDecodeError as exc:
        sys.exit(f"{spec_path.name} is not valid JSON: line {exc.lineno}, {exc.msg}")

    # The whole spec is validated first, not each panel in isolation: a bad icon
    # name in panel 4 should stop the run, not produce three good previews and
    # then a stack trace.
    errs = B.validate(spec)
    if errs:
        print(f"{spec_path.name} has {len(errs)} problem(s):\n")
        for e in errs:
            print(f"  - {e}")
        return None

    panels = spec["panels"]
    if only is not None:
        if not 1 <= only <= len(panels):
            sys.exit(f"--panel {only} is out of range: this spec has "
                     f"{len(panels)} panel(s)")
        chosen = [(only, panels[only - 1])]
    else:
        chosen = list(enumerate(panels, 1))

    # When the spec names no width the build picks one, and it picks the width
    # that suits EVERY panel. A single-panel preview left to choose for itself
    # would pick a narrower one, and the layout is width-dependent — so the
    # preview would differ from the board it is supposed to show. Settle the
    # width once, against the whole spec, and pin it into every panel.
    if "panel_w" not in spec:
        # A copy: fit_width builds probes, and writing the answer back into the
        # caller's own dict would hand them a spec they did not write.
        spec = dict(spec)
        # fit_width returns None when no width in range works. Pin the
        # starting width anyway — that is exactly what build() draws the board
        # at, and leaving the key absent let each panel pick its own instead,
        # so the preview showed a panel the board does not contain.
        spec["panel_w"] = B.fit_width(spec) or B.WIDTH_START

    out_dir = pathlib.Path(out_dir) if out_dir else \
        pathlib.Path.cwd() / "boards" / f"{spec_path.stem}-panels"
    out_dir.mkdir(parents=True, exist_ok=True)

    written, total = [], 0
    for n, panel in chosen:
        dest = out_dir / f"panel-{n}-{slug(panel.get('head', n))}.excalidraw"
        sub = {k: spec[k] for k in CARRIED if k in spec}
        sub["panels"] = [panel]
        sub["out"] = str(dest)

        print(f"\npanel {n}/{len(panels)} — {panel.get('head', '(untitled)')}")
        # Notes are about the whole spec's colours, so they belong on the first
        # panel only; repeating them once per panel buries the panel reports.
        b, problems = B.build(sub, notes=(n == chosen[0][0]))
        b.save(dest)
        print(f"  problems: {problems}")
        total += problems
        written.append(dest)

    print(f"\n{len(written)} panel file(s) in {out_dir}")
    print(f"total problems: {total}")
    if png:
        _png(written)
    else:
        print("Open each one fit-to-screen. --png renders them beside the files.")
    return total


def _png(paths):
    # export_png calls sys.exit() at IMPORT time when Playwright is missing, so
    # the SystemExit comes out of the import, not out of the call. Catching only
    # ImportError round the import let it escape and killed a clean run with
    # exit 1 after it had already reported "total problems: 0".
    try:
        import export_png
        export_png.export([str(p) for p in paths])
    except SystemExit as exc:
        print(f"  (--png skipped: {exc})")
    except ImportError as exc:                       # pragma: no cover
        print(f"  (--png needs export_png: {exc})")


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        sys.exit(__doc__)
    spec, out_dir, only, png = args[0], None, None, False
    i = 1
    while i < len(args):
        a = args[i]
        if a == "--out" and i + 1 < len(args):
            out_dir = args[i + 1]
            i += 2
        elif a == "--panel" and i + 1 < len(args):
            try:
                only = int(args[i + 1])
            except ValueError:
                sys.exit(f"--panel wants a number, got {args[i + 1]!r}")
            i += 2
        elif a == "--png":
            png = True
            i += 1
        else:
            sys.exit(f"unknown argument {a!r}\n\n{__doc__}")
    total = preview(spec, out_dir, only, png)
    # Same contract as build.py: a non-zero exit means something needs fixing.
    return 1 if total is None or total else 0


if __name__ == "__main__":
    sys.exit(main())
