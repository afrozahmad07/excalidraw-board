#!/usr/bin/env python3
"""Build a multi-panel board from library icons and primitives — no image spend.

    python3 scripts/build.py <spec.json>

Every mark is a native Excalidraw element — community-library icons and drawn
primitives — so a board costs nothing and renders identically on every run.

A panel names a `layout` and lists its content. See `specs/layouts-tour.json`
for one panel per layout, and `specs/theme-demo.json` for a themed board.

Two checks run while the board is drawn, and both report loudly:

  bounds     — every mark inside its own panel. An earlier hand-placed version
               pushed icons and labels out onto the caption, which is invisible
               at board zoom and therefore shipped.
  collisions — no two pieces of lettering overlapping. Same reason.

They set the problem count and the exit code. **The file is written either way**,
on purpose — a broken board is easier to fix once you have opened it — so the
exit code, not the presence of the file, is the signal.

A third check runs before anything is drawn and DOES stop the write: contrast.
Lettering that cannot be seen against its own panel is a validation error, so no
file appears at all. A wash or a line colour merely too pale earns a note.
"""

import contextlib
import io
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from excalidraw_kit import Board, txt, rect, arrow, measure   # noqa: E402
import scene                                                  # noqa: E402
import library as lib                                         # noqa: E402

MARGIN = 46

# Contrast floors, measured with scene.contrast() against the colours this skill
# already ships, so a default board can never trip them. The shipped washes run
# 1.14 (mint) to 1.43 (rose) and the rejected "lemon" scored 1.10, which is
# where the wash floor comes from. Text runs 3.32 (title) to 16.4 (ink), and the
# palest icon_tint on offer is orange at 2.44.
WASH_NOTE = 1.10      # a wash below this is not visible on the panel
TINT_NOTE = 2.00      # a line colour below this is not readable
TEXT_NOTE = 3.00      # lettering below this is hard work
TEXT_FAIL = 1.50      # lettering below this is simply not there


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
    """Every mark inside its own panel.

    Extents are normalised because an arrow pointing left or up carries a
    NEGATIVE width or height: its x is the tail, and x + width is the head. Read
    literally, both comparisons then test the wrong end, and an arrow reaching
    266px past the left margin was reported as fine. Back edges out of a Mermaid
    import are exactly that shape.
    """
    bad = []
    for e in elements:
        x1 = min(e["x"], e["x"] + e.get("width", 0))
        x2 = max(e["x"], e["x"] + e.get("width", 0))
        y1 = min(e["y"], e["y"] + e.get("height", 0))
        y2 = max(e["y"], e["y"] + e.get("height", 0))
        if (x1 < x + MARGIN or y1 < y + MARGIN
                or x2 > x + w - MARGIN or y2 > y + h - MARGIN):
            bad.append(e)
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


# --------------------------------------------------------------- validation

REQUIRED = {"flow": ("nodes",), "layers": ("bands",), "hub": ("centre", "items"),
            "row": ("items",), "grid": ("items",), "pair": ("left", "right"),
            "stack": ("rows",), "poster": ("items",)}


HEX = re.compile(r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def is_colour(v, allow_transparent=False):
    if allow_transparent and v == "transparent":
        return True
    return isinstance(v, str) and bool(HEX.match(v))


def validate_theme(theme):
    """A theme is eleven named colours plus two colour maps. Nothing else.

    Checked before it is applied, because a typo here does not throw — it
    silently paints the whole board a colour nobody asked for.
    """
    errs = []
    if theme is None:
        return errs
    if not isinstance(theme, dict):
        return [f'"theme" must be an object, got {type(theme).__name__}']

    allowed = set(scene.THEME_KEYS) | {"palette", "inks"}
    for key in sorted(set(theme) - allowed):
        errs.append(f'theme: unknown key {key!r}. '
                    f'Available: {", ".join(sorted(allowed))}')
    for key in scene.THEME_KEYS:
        if key in theme and not is_colour(theme[key]):
            errs.append(f'theme: "{key}" must be a #hex colour, got {theme[key]!r}')
    for block in ("palette", "inks"):
        entries = theme.get(block)
        if entries is None:
            continue
        if not isinstance(entries, dict):
            errs.append(f'theme: "{block}" must be an object of name -> "#hex", '
                        f'got {type(entries).__name__}')
            continue
        for name, val in entries.items():
            if not is_colour(val, allow_transparent=(block == "palette")):
                errs.append(f'theme: {block}.{name} must be a #hex colour, '
                            f'got {val!r}')
    return errs


def spec_colours(spec):
    """Every wash and icon_tint the spec actually reaches for, with the panel
    each came from — so a contrast note can say where to go and fix it."""
    washes, tints, letters = {}, {}, {}
    for i, p in enumerate(spec.get("panels", [])):
        where = p.get("head", f"panel {i + 1}")
        pools = [p.get("items", []), p.get("nodes", []), p.get("zones", []),
                 p.get("rows", []), p.get("bands", [])]
        for band in p.get("bands", []):
            pools.append(band.get("items", []))
        flat = [it for pool in pools for it in pool if isinstance(it, dict)]
        flat += [p[k] for k in ("centre", "left", "right", "gate", "source",
                                "aside") if isinstance(p.get(k), dict)]
        for it in flat:
            for key, bucket in (("wash", washes), ("tint", washes),
                                ("icon_tint", tints)):
                if it.get(key):
                    bucket.setdefault(it[key], where)
        # A panel carries a marker tint of its own, and a poster edge carries a
        # line colour. Both are drawn; neither was being measured.
        if p.get("tint"):
            washes.setdefault(p["tint"], where)
        for e in p.get("edges", []):
            if isinstance(e, dict) and e.get("colour"):
                tints.setdefault(e["colour"], where)
        # A poster note is lettering, so it belongs with the text checks, not
        # with the line ones. Collected separately for that reason.
        for nt in p.get("notes", []):
            if isinstance(nt, dict) and nt.get("colour"):
                letters.setdefault(nt["colour"], where)
    return washes, tints, letters


def contrast_report(spec):
    """(errors, notes) on whether the colours in play can actually be seen.

    Split deliberately: a wash a shade too pale is the author's call and only
    earns a note, but lettering that scores 1.2 against its own panel is a board
    with nothing on it, and that fails the build.
    """
    errs, notes = [], []
    panel = scene.PANEL_BG
    # The title sits outside the frame, on the canvas — and a spec may set
    # "background" at the top level without a theme, so the canvas is not always
    # scene.BACKGROUND. Score the title against whatever will actually be there.
    canvas = spec.get("background", scene.BACKGROUND)

    def check(name, fg, bg, floor, fail=None):
        ratio = scene.contrast(fg, bg)
        if ratio is None or ratio >= floor:
            return
        line = (f'{name} ({fg}) scores {ratio:.2f} against {bg} — '
                f'below {floor:.2f}')
        if fail is not None and ratio < fail:
            errs.append(f'theme: {line}. It will not be visible. '
                        f'Move it further from "panel", or change "panel".')
        else:
            notes.append(f'note: {line}')

    for name, value, ground in (("ink", scene.INK, panel),
                                ("muted text", scene.MUTED, panel),
                                ("acronym text", scene.FULL_C, panel),
                                # Both of these sit OUTSIDE the frame, on the
                                # canvas. Scoring them against the panel reads
                                # the wrong ground whenever the two differ.
                                ("title", scene.TITLE_C, canvas),
                                ("caption", scene.MUTED, canvas)):
        check(name, value, ground, TEXT_NOTE, TEXT_FAIL)

    washes, tints, letters = spec_colours(spec)
    for name, where in sorted(washes.items()):
        check(f'wash {name!r} on {where!r}', scene.colour(name), panel, WASH_NOTE)
        # A label inside a washed box sits on the WASH, not on the panel. The
        # wash can clear the panel comfortably and still swallow the ink.
        check(f'ink on wash {name!r} in {where!r}', scene.INK,
              scene.colour(name), TEXT_NOTE, TEXT_FAIL)
    for name, where in sorted(tints.items()):
        check(f'icon_tint {name!r} on {where!r}',
              scene.stroke_colour(name), panel, TINT_NOTE)
    for name, where in sorted(letters.items()):
        check(f'note colour {name!r} on {where!r}', scene.stroke_colour(name),
              panel, TEXT_NOTE, TEXT_FAIL)
    return errs, notes


def validate(spec):
    """Fail with a sentence a person can act on, before anything is drawn.

    A bad spec used to surface as a KeyError or a stack trace from deep inside
    a layout, which tells you nothing about which panel is wrong.
    """
    errs = validate_theme(spec.get("theme"))
    if errs:
        # A broken theme is not applied, so every wash name below would be
        # checked against the wrong palette. Stop here and say only that.
        return errs
    # Applied before the panels are checked: a theme may ADD wash names, and
    # those must pass validation rather than be reported as unknown colours.
    # Restored at the end, because validating one spec should not leave its
    # colours behind for whatever the caller does next. build() applies its own.
    saved_theme = scene.theme_snapshot()
    scene.apply_theme(spec.get("theme"))

    if "out" not in spec:
        errs.append('spec is missing "out" — where to write the .excalidraw file')
    panels = spec.get("panels")
    if not panels:
        errs.append('spec is missing "panels", or it is empty')
        # The theme was applied above. Every return has to put it back, not
        # only the last one.
        scene.theme_restore(saved_theme)
        return errs

    for i, p in enumerate(panels):
        where = f'panel {i + 1} ({p.get("head", "untitled")!r})'
        for key in ("head", "caption"):
            if key not in p:
                errs.append(f'{where}: missing "{key}"')
        layout = p.get("layout")
        if layout is None:
            errs.append(f'{where}: missing "layout" — one of {", ".join(sorted(scene.LAYOUTS))}')
            continue
        if layout not in scene.LAYOUTS:
            errs.append(f'{where}: unknown layout {layout!r}. '
                        f'Available: {", ".join(sorted(scene.LAYOUTS))}')
            continue
        for key in REQUIRED[layout]:
            if key not in p:
                errs.append(f'{where}: layout "{layout}" needs "{key}"')

        items = list(p.get("items", []))
        for band in p.get("bands", []):
            items += band.get("items", [])
        for k in ("centre", "left", "right", "gate", "source", "aside"):
            if isinstance(p.get(k), dict):
                items.append(p[k])
        for it in items:
            errs += validate_item(it, where)

        # Flow nodes, poster zones, layer bands and stack rows are not "items" —
        # they carry no shape and no icon, so validate_item cannot look at them.
        # Their wash was therefore never checked, and an unknown name is written
        # into the file verbatim as a colour Excalidraw will not understand.
        for group in ("nodes", "zones", "bands", "rows"):
            for thing in p.get(group, []):
                if isinstance(thing, dict):
                    errs += validate_wash(thing, f'{where}, {group[:-1]} '
                                          f'{thing.get("id", thing.get("label", "?"))!r}')
        # A panel carries a marker tint; a poster edge and a poster note each
        # carry a line colour. All three are drawn. The contrast pass was
        # extended to measure them, but contrast() returns None for a name it
        # cannot parse and a None is treated as a pass — so an unknown name is
        # still written into the file unless it is refused here.
        errs += validate_wash(p, f'{where}, the panel')
        for kind in ("edges", "notes"):
            for thing in p.get(kind, []):
                if isinstance(thing, dict) and thing.get("colour"):
                    errs += validate_line(thing["colour"],
                                          f'{where}, {kind[:-1]} colour')

        if layout == "flow":
            ids = {n.get("id") for n in p.get("nodes", [])}
            for n in p.get("nodes", []):
                if not n.get("id"):
                    errs.append(f'{where}: every flow node needs an "id"')
                if not n.get("label"):
                    errs.append(f'{where}: flow node {n.get("id")!r} needs a "label"')
            for e in p.get("edges", []):
                for end in e[:2]:
                    if end not in ids:
                        errs.append(f'{where}: edge points at unknown node {end!r}. '
                                    f'Known ids: {", ".join(sorted(x for x in ids if x))}')


    errs += contrast_report(spec)[0]
    scene.theme_restore(saved_theme)
    return errs


def validate_wash(thing, where):
    """Just the colour names on something that is not an item.

    `is_colour`, not `startswith("#")`. A leading hash was the whole test, so
    "#zzzzzz" passed every one of these and went into the file verbatim — while
    the same string in a theme was refused by the real validator sitting a
    hundred lines above.
    """
    errs = []
    for key in ("wash", "tint"):
        val = thing.get(key)
        if val and val not in scene.PALETTE and not is_colour(val, True):
            errs.append(f'{where}: unknown {key} {val!r}. '
                        f'Use one of {", ".join(sorted(scene.PALETTE))} or a #hex')
    return errs


def validate_line(value, where):
    """A colour used for a LINE or for lettering, not for a wash."""
    if value in scene.INKS or value in scene.PALETTE or is_colour(value):
        return []
    return [f'{where}: unknown colour {value!r}. '
            f'Use one of {", ".join(sorted(scene.INKS))} or a #hex']


def validate_item(it, where):
    errs = []
    if "shape" in it:
        if it["shape"] not in scene.SHAPES:
            errs.append(f'{where}: unknown shape {it["shape"]!r}. '
                        f'Available: {", ".join(sorted(scene.SHAPES))}')
    elif "icon" in it:
        ref = it["icon"]
        if not (isinstance(ref, (list, tuple)) and len(ref) == 2):
            errs.append(f'{where}: "icon" must be [library, item-name], got {ref!r}')
        else:
            src = scene.LIBS.get(ref[0], ref[0])
            if "/" not in src:
                errs.append(f'{where}: unknown library {ref[0]!r}. '
                            f'Shorthands: {", ".join(sorted(scene.LIBS))} — or pass '
                            f'a full owner/name.excalidrawlib')
            else:
                try:
                    if not lib.find_item(src, ref[1]):
                        names = [x["name"] for x in lib.load(src)][:8]
                        errs.append(f'{where}: {ref[1]!r} not found in {ref[0]}. '
                                    f'First few available: {", ".join(names)}')
                except Exception as exc:
                    errs.append(f'{where}: could not read library {ref[0]!r} ({exc})')
    else:
        errs.append(f'{where}: item has neither "shape" nor "icon": {it!r}')
    wash = it.get("wash") or it.get("tint")
    if wash and wash not in scene.PALETTE and not is_colour(wash, True):
        errs.append(f'{where}: unknown colour {wash!r}. '
                    f'Use one of {", ".join(sorted(scene.PALETTE))} or a #hex')
    tint = it.get("icon_tint")
    if tint and tint not in scene.INKS and tint not in scene.PALETTE \
            and not is_colour(tint):
        errs.append(f'{where}: unknown icon_tint {tint!r}. '
                    f'Use one of {", ".join(sorted(scene.INKS))} or a #hex')
    if tint and "icon" not in it:
        errs.append(f'{where}: "icon_tint" recolours a library icon, but this '
                    f'item is a {it.get("shape", "shape")!r} — '
                    f'set its colours with "wash" instead')
    return errs


# One ceiling for both searches. They used to disagree — the width finder gave
# up at 2560 and returned 1180 in silence, while the suggestion printed
# afterwards searched to 3540 and named a width the finder was never allowed to
# reach. A board came out with 36 problems beside a line saying which width
# would have worked.
WIDTH_START = 1180
WIDTH_STEP = 60
WIDTH_CAP = 3600


def fit_width(spec, start=WIDTH_START, step=WIDTH_STEP, cap=WIDTH_CAP):
    """The narrowest panel width that draws every panel clean, or None.

    Only consulted when the spec does not name one. 1180 is a default, not a
    request: five steps with labelled arrows do not fit it, and of the three
    options — draw outside the frame, squash the boxes, or use more width —
    only the last leaves a board anyone can read.

    Returns None when nothing in range works, rather than the starting width.
    Handing back a width already proven not to work, under a docstring promising
    one that does, is how the caller ends up drawing a broken board quietly.
    """
    saved_n, saved_bounds = scene._n[0], scene.BOUNDS[0]
    saved_theme = scene.theme_snapshot()
    try:
        for w in range(start, cap + 1, step):
            probe = dict(spec)
            probe["panel_w"] = w
            with contextlib.redirect_stdout(io.StringIO()):
                if build(probe, notes=False, suggest=False)[1] == 0:
                    return w
    finally:
        scene._n[0], scene.BOUNDS[0] = saved_n, saved_bounds
        scene.theme_restore(saved_theme)
    return None


def widths_that_work(spec, panel, start):
    """The narrowest panel_w that draws this flow panel clean, or None.

    Measured, not predicted. An earlier version calculated the width from the
    column labels and came back 300px short, because it did not account for the
    room the arrow labels need in the gaps. A number that is wrong is worse than
    no number, so this widens a throwaway copy until the panel actually passes.
    """
    if panel.get("layout") != "flow":
        return None
    saved_n, saved_bounds = scene._n[0], scene.BOUNDS[0]
    saved_theme = scene.theme_snapshot()
    try:
        for w in range(int(start) + WIDTH_STEP, WIDTH_CAP + 1, WIDTH_STEP):
            probe = {k: v for k, v in spec.items() if k != "panels"}
            probe["panels"] = [panel]
            probe["panel_w"] = w
            with contextlib.redirect_stdout(io.StringIO()):
                if build(probe, notes=False, suggest=False)[1] == 0:
                    return w
    finally:
        scene._n[0], scene.BOUNDS[0] = saved_n, saved_bounds
        scene.theme_restore(saved_theme)
    return None


def build(spec, notes=True, suggest=True):
    # Idempotent, and it resets first — so building several specs in one process
    # (which preview_panels.py does) never inherits the last one's colours.
    scene.apply_theme(spec.get("theme"))
    # Element ids come from a running counter. Resetting it per board means a
    # second build in the same process is byte-identical to the first, which is
    # what makes preview_panels.py reproducible rather than merely repeatable.
    scene._n[0] = 0
    if notes:
        for note in contrast_report(spec)[1]:
            print(f"  {note}")
    b = Board(background=spec.get("background", scene.BACKGROUND))
    pw = spec.get("panel_w")
    if pw is None:
        pw = fit_width(spec)
        if pw is None:
            pw = WIDTH_START
            if notes:
                print(f"  note: no width up to {WIDTH_CAP} draws this cleanly, "
                      f"so it is drawn at {WIDTH_START} and the problems below "
                      f"are real. Split it across panels, or shorten the "
                      f"longest labels.")
        elif notes and pw != WIDTH_START:
            print(f'  note: widened the panel to {pw} so everything fits. '
                  f'Set "panel_w" in the spec to choose your own.')
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
        scene.label(b, p["head"], x + pw / 2, y - 90, 40, scene.TITLE_C)
        b.add(rect(f"frame{i}", x, y, pw, ph, stroke=scene.FRAME,
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
        hit = (check_bounds(body[2:], x, y, pw, ph, p["head"][:24])
               + check_collisions(body, p["head"][:24]))
        problems += hit
        if hit and suggest:
            fits = widths_that_work(spec, p, pw)
            if fits:
                print(f"    -> this panel draws clean at \"panel_w\": {fits} "
                      f"(it has {pw})")

        # An empty caption draws an empty text element — a zero-width mark you
        # can still select and drag. An import that has no caption to give
        # should leave nothing behind, not that.
        if p.get("caption"):
            cap = wrap(p["caption"], 22, pw - 60)
            cw, _ = measure(cap, 22)
            e = txt(f"cap{i}", x + (pw - cw) / 2, y + ph + 34, cap, 22,
                    scene.MUTED)
            e["textAlign"] = "center"
            b.add(e)

        if i < len(spec["panels"]) - 1:
            b.add(arrow(f"flow{i}", x + pw + 70, y + ph / 2, gap - 140, 0,
                        color=scene.INK, curved=False))
    return b, problems


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    spec_path = pathlib.Path(sys.argv[1])
    try:
        spec = json.loads(spec_path.read_text())
    except json.JSONDecodeError as exc:
        sys.exit(f"{spec_path.name} is not valid JSON: line {exc.lineno}, {exc.msg}")

    errs = validate(spec)
    if errs:
        print(f"{spec_path.name} has {len(errs)} problem(s):\n")
        for e in errs:
            print(f"  - {e}")
        sys.exit(1)

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
