#!/usr/bin/env python3
"""Prove the build still works, from a cold clone, without opening anything.

    python3 scripts/selftest.py

Nothing here needs the network beyond the icon cache, and nothing needs
Playwright. It builds every shipped spec, then deliberately breaks things to
confirm each check can still fail — a check that cannot fail is not a check.

Sixteen groups:

    specs         every spec in specs/ builds with problems: 0
    determinism   the same spec built twice is byte-identical
    theme         a themed board does not leak its colours into the next one
    themereach    every layout draws in the themed colours, not the shipped ones
    guards        the build's own checks, and promises nothing asserted
    coverage      colours the validator and the contrast report were missing
    grid          a grid row lines its icons and labels up on one baseline
    flowfit       a flow shrinks to fit, and says so when it cannot
    preview       a preview panel matches that panel in the full board exactly
    tint          icon_tint recolours visible lines, only those, in all three
                  layouts that stamp an icon
    colour        the contrast and theme checks each fire on a bad value
    specerr       a bad spec is refused with a sentence naming the problem
    mermaid       flowcharts parse to the expected shape and build clean
    mermaidplace  each rank sits where it should, in all four directions
    mermaidtext   node and edge text survives quoting, nesting and markup
    mermaiderr    an unsupported diagram is refused by name
"""

import contextlib
import copy
import io
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import build as B                                             # noqa: E402
import library as lib                                         # noqa: E402
import mermaid_to_spec as M                                   # noqa: E402
import scene                                                  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESULTS = []


def check(group, name, ok, detail=""):
    RESULTS.append((group, name, bool(ok), detail))
    if not ok:
        print(f"  FAIL [{group}] {name}" + (f" — {detail}" if detail else ""))
    return bool(ok)


def quietly(fn, *a, **kw):
    """Run something noisy and hand back (result, what it printed)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = fn(*a, **kw)
    return out, buf.getvalue()



def outside(board, _spec=None):
    """Anything outside the panel, on EITHER axis.

    Measured against the frame the build actually drew, because a spec need
    not name a width. This checked only x until a review pushed every mark
    200px above the panel top and watched it report nothing.
    """
    frame = next(e for e in board.elements if e["id"].startswith("frame"))
    left, right = frame["x"] + 46, frame["x"] + frame["width"] - 46
    top, bottom = frame["y"] + 46, frame["y"] + frame["height"] - 46
    bad = []
    for e in board.elements:
        # The title sits above the frame and the caption below it, both by
        # design; everything else belongs inside.
        if e["id"].startswith(("frame", "cap")) or e["y"] < frame["y"]:
            continue
        # Normalised, for the same reason check_bounds is: an arrow
        # pointing left or up carries a negative width or height. The
        # product fix landed without this helper being corrected too.
        x1 = min(e["x"], e["x"] + e.get("width", 0))
        x2 = max(e["x"], e["x"] + e.get("width", 0))
        y1 = min(e["y"], e["y"] + e.get("height", 0))
        y2 = max(e["y"], e["y"] + e.get("height", 0))
        if x1 < left or x2 > right or y1 < top or y2 > bottom:
            bad.append((e["id"], e.get("text"),
                        round(e["x"] - frame["x"]), round(e["y"] - frame["y"])))
    return bad


def build_spec(spec):
    return quietly(B.build, copy.deepcopy(spec))[0]


# --------------------------------------------------------------------- specs

def specs():
    files = sorted((ROOT / "specs").glob("*.json"))
    check("specs", "there are specs to build", files)
    for f in files:
        spec = json.loads(f.read_text())
        errs = quietly(B.validate, spec)[0]
        if not check("specs", f"{f.name} validates", not errs, "; ".join(errs[:2])):
            continue
        _board, problems = build_spec(spec)
        check("specs", f"{f.name} builds clean", problems == 0,
              f"{problems} bounds/collision problem(s)")

    # A Mermaid import has no caption to give. An empty one used to draw an
    # empty text element — a zero-width mark you can still select and drag.
    blank = {"out": "unused", "panels": [{
        "head": "h", "caption": "", "layout": "flow",
        "nodes": [{"id": "a", "label": "A", "col": 0, "row": 0}]}]}
    board = build_spec(blank)[0]
    check("specs", "an empty caption leaves nothing behind",
          not [e for e in board.elements
               if e.get("type") == "text" and not e.get("text", "").strip()])


def spec_or_skip(group, name):
    """Load a named spec, or fail loudly rather than taking a group down.

    `specs/tailscale-how-it-works.json` is gitignored and `theme-demo.json` was
    untracked, so on a fresh clone three groups used to die on a
    FileNotFoundError and nineteen checks silently stopped existing — while the
    summary still printed a confident total.
    """
    path = ROOT / "specs" / name
    if not path.exists():
        check(group, f"the fixture {name} is present", False,
              "this group cannot run without it")
        return None
    return json.loads(path.read_text())


def determinism():
    for name in ("layouts-tour.json", "theme-demo.json"):
        spec = spec_or_skip("determinism", name)
        if spec is None:
            continue
        one = json.dumps(build_spec(spec)[0].to_dict())
        two = json.dumps(build_spec(spec)[0].to_dict())
        check("determinism", f"{name} rebuilds byte-identically", one == two)


# --------------------------------------------------------------------- theme

def theme():
    plain = spec_or_skip("theme", "flow-demo.json")
    themed = spec_or_skip("theme", "theme-demo.json")
    if plain is None or themed is None:
        return

    def palette_of(spec):
        b = build_spec(spec)[0]
        return {e["strokeColor"] for e in b.elements} | \
               {e["backgroundColor"] for e in b.elements}

    before = palette_of(plain)
    dark = palette_of(themed)
    after = palette_of(plain)
    check("theme", "the theme reaches the board", "#e9edf2" in dark)
    check("theme", "the default board is unchanged by a themed build",
          before == after, f"{sorted(before ^ after)}")
    check("theme", "the globals are back to the shipped values",
          scene.INK == "#1e1e1e" and scene.PALETTE["sky"] == "#d0ebff"
          and scene.BACKGROUND == "#fdf6e3")

    # A theme may ADD a wash name; validation has to see the merged palette.
    extra = copy.deepcopy(themed)
    extra["theme"]["palette"]["brand"] = "#3b2f6b"
    extra["panels"][0]["nodes"][0]["wash"] = "brand"
    check("theme", "a wash the theme added is accepted",
          not quietly(B.validate, extra)[0])

    # A theme that names one wash must not take the other five with it: the
    # primitives ask for washes by name, so doc() would die on a missing key.
    scene.apply_theme({"palette": {"mint": "#123456"}})
    check("theme", "a partial palette keeps the other washes",
          set(scene.PALETTE) >= {"mint", "lilac", "sky", "peach", "rose",
                                 "sage", "none"},
          f"left with {sorted(scene.PALETTE)}")
    scene.reset_theme()

    partial = {"out": "unused", "theme": {"palette": {"mint": "#123456"}},
               "panels": [{"head": "h", "caption": "", "layout": "grid",
                           "items": [{"shape": "doc", "label": "a file"}]}]}
    errs = quietly(B.validate, partial)[0]
    if check("theme", "a partial palette still validates", not errs,
             "; ".join(errs[:1])):
        try:
            build_spec(partial)
            check("theme", "a shape still finds the wash it draws with", True)
        except KeyError as exc:
            check("theme", "a shape still finds the wash it draws with", False,
                  f"the primitives lost {exc}")
    scene.reset_theme()


def themereach():
    """Does the theme reach every mark, or only the ones a spec happens to use?

    Every check here was added after a review found the ink colour never
    reaching the `row` and `layers` layouts: `label()` took its colour as a
    default argument, which binds once at import, so a theme that rebound INK
    was invisible to the three call sites that omitted the argument. The board
    reported no problems because the contrast check reads the themed value —
    the one that was never drawn.
    """
    # Every one of the eleven keys, each a value that appears nowhere else, so
    # a key that reaches nothing can be named rather than guessed at.
    dark = {"background": "#12161d", "panel": "#1a2029", "ink": "#e9edf2",
            "muted": "#9aa6b4", "title": "#ffb454", "frame": "#39434f",
            "zone": "#4a5665", "hair": "#5b6775", "card": "#232b36",
            "accent": "#c495f0", "full": "#e0a86a",
            "palette": {"mint": "#12453c", "sky": "#123952",
                        "peach": "#4a3418", "lilac": "#332a55",
                        "rose": "#4d2028", "sage": "#1e4326"}}

    # One panel per layout, all in one themed board, so no layout can be
    # excluded just because no shipped spec happens to use it.
    icon = ["net", "Server"]
    panels = [
        {"head": "flow", "caption": "", "layout": "flow",
         "nodes": [{"id": "a", "label": "One", "col": 0, "row": 0},
                   {"id": "b", "label": "Two", "col": 1, "row": 0}],
         "edges": [["a", "b", "then"]]},
        {"head": "grid", "caption": "", "layout": "grid", "cols": 2,
         "items": [{"icon": icon, "label": "one", "note": "a note",
                    "full": "what the acronym stands for"},
                   {"icon": icon, "label": "two"}]},
        {"head": "row", "caption": "", "layout": "row",
         "source": {"shape": "cloud", "label": "the source", "size": 260},
         "items": [{"icon": icon, "label": "one"},
                   {"icon": icon, "label": "two"}]},
        {"head": "layers", "caption": "", "layout": "layers",
         "bands": [{"label": "tier one", "note": "the top",
                    "items": [{"icon": icon, "label": "one"}]},
                   {"label": "tier two",
                    "items": [{"icon": icon, "label": "two"}]}]},
        {"head": "hub", "caption": "", "layout": "hub", "item_size": 90,
         "centre": {"icon": icon, "label": "middle", "size": 110},
         "items": [{"icon": ["net", "Client"], "label": f"n{i}"}
                   for i in range(4)]},
        {"head": "pair", "caption": "", "layout": "pair", "blocked": True,
         "left": {"shape": "doc", "label": "before"},
         "right": {"shape": "padlock", "label": "after"}},
        {"head": "stack", "caption": "", "layout": "stack",
         "rows": [{"label": "top"}, {"label": "bottom"}]},
        {"head": "poster", "caption": "", "layout": "poster",
         "zones": [{"label": "a zone", "x": .05, "y": .09, "w": .9, "h": .74}],
         "items": [{"id": "p", "icon": icon, "label": "inside", "x": .5,
                    "y": .45, "note": "a note"}]},
    ]
    check("themereach", "every layout is covered here",
          {p["layout"] for p in panels} == set(scene.LAYOUTS),
          f"missing {set(scene.LAYOUTS) - {p['layout'] for p in panels}}")

    spec = {"out": "unused", "theme": dark, "panel_w": 1500, "panel_h": 860,
            "panels": panels}
    errs = quietly(B.validate, spec)[0]
    if not check("themereach", "the all-layouts themed spec validates", not errs,
                 "; ".join(errs[:2])):
        return
    board, problems = build_spec(spec)
    check("themereach", "and it builds clean", problems == 0)

    # Every colour anywhere in the file, not only the lettering. Scanning text
    # alone left five of the eleven keys — frame, zone, hair, card, accent —
    # able to reach nothing at all with the suite still green.
    used = {e["strokeColor"] for e in board.elements}
    used |= {e["backgroundColor"] for e in board.elements}
    used.add(board.background)

    missing = {k: v for k, v in dark.items()
               if isinstance(v, str) and v not in used}
    check("themereach", "every one of the eleven theme colours reaches the board",
          not missing, f"these reached nothing: {missing}")

    replaced = {v for k, v in scene._DEFAULTS.items()}
    stale = sorted(c for c in used & replaced)
    check("themereach", "and no shipped default is still drawn anywhere",
          not stale, f"still drawn: {stale}")

    # And every piece of lettering can actually be seen on what is behind it.
    worst = None
    for e in board.elements:
        if e.get("type") != "text" or not e.get("text", "").strip():
            continue
        ground = dark["background"] if e["id"].startswith("cap") \
            or e["y"] < 260 else dark["panel"]
        r = scene.contrast(e["strokeColor"], ground)
        if r is not None and (worst is None or r < worst[0]):
            worst = (r, e.get("text", "")[:24], e["strokeColor"])
    # 1.5 written out, not read from TEXT_FAIL: a check that moves with the
    # constant it is testing gets easier every time the constant is lowered.
    check("themereach", "the least readable label still clears 1.5",
          worst and worst[0] >= 1.5,
          f"worst is {worst[0]:.2f} on {worst[1]!r} in {worst[2]}" if worst else "none")

    # label() must take its colour at call time, not as a default argument.
    import inspect
    check("themereach", "label() does not freeze a colour in its signature",
          inspect.signature(scene.label).parameters["color"].default is None,
          f"default is {inspect.signature(scene.label).parameters['color'].default!r}")
    scene.reset_theme()


def guards():
    """The build's own checks, and the promises nothing was asserting.

    Every check here exists because a review proved the suite stayed green
    while the behaviour was removed.
    """
    # check_collisions had almost no direct guard: zeroing it out reddened one
    # check, and only as a side effect. Two labels on the same spot must be
    # caught, and must be caught by the collision check rather than by bounds.
    stacked = {"out": "unused", "panels": [{
        "head": "h", "caption": "", "layout": "poster",
        "items": [{"id": "a", "shape": "doc", "label": "one label here",
                   "x": .5, "y": .5},
                  {"id": "b", "shape": "doc", "label": "another label here",
                   "x": .5, "y": .5}]}]}
    (board, problems), printed = quietly(B.build, copy.deepcopy(stacked))
    check("guards", "two labels drawn on the same spot are caught",
          problems > 0, "the collision check did not fire")
    check("guards", "and it is the collision check that reports it",
          "OVERLAP" in printed and "BOUNDS" not in printed,
          f"got {printed.strip().splitlines()[:1]}")

    # The caption was checked by nothing at all: build() takes its bounds and
    # collision slice before appending it, and outside() skips it by id.
    long_caption = "A caption long enough to need wrapping. " * 4
    spec = {"out": "unused", "panel_w": 1180, "panels": [{
        "head": "h", "caption": long_caption, "layout": "flow",
        "nodes": [{"id": "a", "label": "A", "col": 0, "row": 0}]}]}
    board = build_spec(spec)[0]
    caps = [e for e in board.elements if e["id"].startswith("cap")]
    if check("guards", "a caption is drawn", len(caps) == 1, f"{len(caps)} found"):
        cap = caps[0]
        check("guards", "a long caption is wrapped, not one endless line",
              "\n" in cap["text"], "no line break in it")
        check("guards", "a caption stays within the width of its panel",
              cap["x"] >= 120 and cap["x"] + cap["width"] <= 120 + 1180,
              f"x {cap['x']:.0f} width {cap['width']:.0f}")

    # fit_width promises the NARROWEST width that works. Nothing tested the word
    # "narrowest" — pinning it to the 2600 cap left the whole suite green.
    wide = {"out": "unused", "panels": [{
        "head": "h", "caption": "", "layout": "flow",
        "nodes": [{"id": f"n{i}", "label": l, "col": i, "row": 0} for i, l in
                  enumerate(["Onboarding", "Underwriting", "Completion",
                             "Reconciliation", "Provisioning"])]}]}
    found = B.fit_width(copy.deepcopy(wide))
    check("guards", "fit_width returns a width that works",
          quietly(B.build, dict(copy.deepcopy(wide), panel_w=found))[0][1] == 0,
          f"{found} does not draw clean")
    narrower = dict(copy.deepcopy(wide), panel_w=found - 60)
    check("guards", f"and nothing narrower works ({found} - 60 fails)",
          quietly(B.build, narrower)[0][1] > 0,
          f"{found - 60} also draws clean, so {found} is not the narrowest")

    # A diagonal arrow crosses open space; only a straight one lives in a gap.
    # Wrapping every label to the gap made the diagonal ones four lines tall and
    # they landed on the boxes below. This is the real onboarding diagram that
    # first showed it.
    branchy = {"out": "unused", "panel_w": 1300, "panels": [{
        "head": "h", "caption": "", "layout": "flow",
        "nodes": [{"id": "a", "label": "Enquiry", "col": 0, "row": 1},
                  {"id": "b", "label": "Discovery call", "col": 1, "row": 1},
                  {"id": "c", "label": "Proposal", "col": 2, "row": 1},
                  {"id": "d", "label": "Deposit", "col": 3, "row": 1},
                  {"id": "e", "label": "Kickoff", "col": 4, "row": 1},
                  {"id": "x", "label": "Not a fit", "col": 2, "row": 0},
                  {"id": "y", "label": "Goes quiet", "col": 3, "row": 0}],
        "edges": [["a", "b"], ["b", "c", "if it fits"],
                  ["b", "x", "if it does not"], ["c", "d", "signed"],
                  ["c", "y", "no reply"], ["d", "e"]]}]}
    check("guards", "a diagonal arrow's label is not squeezed into a column gap",
          build_spec(branchy)[1] == 0,
          "a branching flow with labelled diagonals does not draw clean")

    # The gap floors stop two boxes touching once everything has been squeezed.
    # Six columns by eight rows in the default panel drives both to the floor.
    squeezed = {"out": "unused", "panel_w": 1180, "panels": [{
        "head": "h", "caption": "", "layout": "flow",
        "nodes": [{"id": f"n{r}{c}", "label": f"Step {r}{c}", "col": c,
                   "row": r} for r in range(8) for c in range(6)]}]}
    board = build_spec(squeezed)[0]
    boxes = [e for e in board.elements
             if e.get("type") == "rectangle" and e["id"].startswith("n")]
    xs = sorted({round(e["x"]) for e in boxes})
    ys = sorted({round(e["y"]) for e in boxes})
    bw, bh = boxes[0]["width"], boxes[0]["height"]
    gx = min((b - a - bw for a, b in zip(xs, xs[1:])), default=999)
    gy = min((b - a - bh for a, b in zip(ys, ys[1:])), default=999)
    # The numbers are written out, not read from MIN_GAP_X / MIN_GAP_Y. A
    # check that reads the constant it is testing moves with it and proves
    # nothing — setting either floor to zero used to leave this green.
    check("guards", "squeezed columns never close below 39px",
          gx >= 39, f"columns end up {gx:.0f} apart")
    check("guards", "squeezed rows never close below 29px",
          gy >= 29, f"rows end up {gy:.0f} apart")

    # Squeezed as far as it goes, every column sits on its own floor — there is
    # nothing left that could have given way.
    labels = ["Discovery call scheduled", "Proposal sent out",
              "Deposit received now", "Kickoff session held",
              "Delivery phase begins", "Retrospective written up"]
    tight = {"out": "unused", "panel_w": 1180, "panels": [{
        "head": "h", "caption": "", "layout": "flow",
        "nodes": [{"id": f"n{i}", "label": l, "col": i, "row": 0}
                  for i, l in enumerate(labels)]}]}
    widths = [round(e["width"]) for e in build_spec(tight)[0].elements
              if e.get("type") == "rectangle" and e["id"].startswith("n")]
    # The property, not six font-metric pixels: no column wider than the floor
    # it was allowed, and no column narrower than its own longest word. A golden
    # list would break on any change to measure() for no behavioural reason.
    floors = [max(150, scene.word_floor([{"label": l}])) for l in labels]
    check("guards", "a flow squeezed to its limit sits on its column floors",
          widths and all(f - 1 <= w <= f + 1 for w, f in zip(widths, floors)),
          f"widths {widths} against floors {floors}"),

    # Two paths no board reaches today, so only a direct call can hold them.
    scene.apply_theme({"ink": "#abcdef", "palette": {"mint": "#111111"}})
    probe = {"out": "unused", "panels": [{
        "head": "h", "caption": "", "layout": "flow",
        "nodes": [{"id": f"n{i}", "label": l, "col": i, "row": 0}
                  for i, l in enumerate(labels)]}]}
    quietly(B.fit_width, probe)
    check("guards", "a width probe leaves the caller's theme exactly as it was",
          scene.INK == "#abcdef" and scene.PALETTE["mint"] == "#111111",
          f"ink is {scene.INK}, mint is {scene.PALETTE['mint']}")

    # And validating a DIFFERENT spec must not leave its colours behind either.
    quietly(B.validate, {"out": "unused", "theme": {"ink": "#123456"},
                         "panels": [{"head": "h", "caption": "", "layout": "flow",
                                     "nodes": [{"id": "a", "label": "A",
                                                "col": 0, "row": 0}]}]})
    check("guards", "validating a spec leaves the caller's theme alone",
          scene.INK == "#abcdef",
          f"validate() left ink as {scene.INK}")
    scene.reset_theme()

    try:
        quietly(B.build, {"out": "unused", "panels": [{
            "head": "h", "layout": "flow",
            "nodes": [{"id": "a", "label": "A", "col": 0, "row": 0}]}]})
        check("guards", "a panel with no caption key does not crash the build", True)
    except KeyError as exc:
        check("guards", "a panel with no caption key does not crash the build",
              False, f"KeyError {exc}")

    # An arrow pointing left or up carries a NEGATIVE width or height: its x is
    # the tail and x + width is the head. Read literally, both bounds
    # comparisons test the wrong end, and an arrow far outside the panel was
    # reported as fine. Mermaid back edges are exactly this shape.
    from excalidraw_kit import arrow as _arrow
    for name, el, why in (
        ("a leftward arrow past the left margin",
         _arrow("a1", 300, 400, -400, 0), "x + width is the head"),
        ("an upward arrow above the top margin",
         _arrow("a2", 300, 400, 0, -400), "y + height is the head"),
        ("a rightward arrow past the right margin",
         _arrow("a3", 1200, 400, 400, 0), "the ordinary case"),
    ):
        _, printed = quietly(B.check_bounds, [el], 120, 260, 1180, 780, "t")
        check("guards", f"{name} is caught", "BOUNDS" in printed, why)

    # Alpha makes a colour invisible whatever its hue. Reading only the RGB
    # bytes scored a fully transparent ink at 21:1 and passed a board whose
    # every letter was see-through.
    check("guards", "a fully transparent colour scores as invisible",
          scene.contrast("#00000000", "#ffffff") == 1.0
          and scene.contrast("#0000", "#ffffff") == 1.0,
          f'8-digit {scene.contrast("#00000000", "#ffffff")}, '
          f'4-digit {scene.contrast("#0000", "#ffffff")}')
    check("guards", "and an opaque one is unaffected",
          round(scene.contrast("#000000", "#ffffff"), 2) == 21.0,
          f'{scene.contrast("#000000", "#ffffff")}')

    # A poster edge names a LINE colour. It was drawn through the wash resolver,
    # which does not know ink names, so "blue" went into the file verbatim while
    # the contrast check scored the hex it should have been.
    poster = {"out": "unused", "panels": [{
        "head": "h", "caption": "", "layout": "poster",
        "items": [{"id": "a", "shape": "doc", "label": "one", "x": .25, "y": .5},
                  {"id": "b", "shape": "doc", "label": "two", "x": .75, "y": .5}],
        "edges": [{"from": "a", "to": "b", "colour": "blue"}]}]}
    drawn = {e["strokeColor"] for e in build_spec(poster)[0].elements
             if e.get("type") == "arrow"}
    check("guards", "a poster edge colour is drawn as the colour it was scored as",
          "blue" not in drawn and scene.INKS["blue"] in drawn,
          f"arrows drawn in {sorted(drawn)}")

    # The importer must not name a width. Predicting the layout's arithmetic
    # produced a panel 1.9x wider than the one that works.
    imported, _g = M.to_spec(M.extract(
        "flowchart LR\n  a[Enquiry] -- forwards it on --> b[Discovery] "
        "-- once approved --> c[Proposal] --> d[Deposit] --> e[Kickoff]"))
    check("guards", "a Mermaid import names no panel width",
          "panel_w" not in imported, f"it pinned {imported.get('panel_w')}")
    if not quietly(B.validate, copy.deepcopy(imported))[0]:
        board, problems = build_spec(imported)
        frame = next(e for e in board.elements if e["id"].startswith("frame"))
        check("guards", "and the width it gets is measured and modest",
              problems == 0 and frame["width"] <= 1800,
              f"{problems} problem(s) at width {frame['width']:.0f}")

    # The loader is memoised, and stamp() deep-copies, so the cache cannot be
    # poisoned by a caller mutating what it got back.
    first = lib.load("dwelle/network-topology-icons.excalidrawlib")
    second = lib.load("dwelle/network-topology-icons.excalidrawlib")
    check("guards", "the icon library is parsed once, not once per lookup",
          first is second, "load() re-parsed the file")
    entry = lib.find_item("dwelle/network-topology-icons.excalidrawlib", "Server")
    before = entry["elements"][0]["strokeColor"]
    lib.stamp(entry, 0, 0, target_w=100, uid="x", tint="#ff0000")
    check("guards", "and stamping does not write back into the cache",
          entry["elements"][0]["strokeColor"] == before,
          f"{before} became {entry['elements'][0]['strokeColor']}")

    # The width finder and the width suggester used to disagree: the finder gave
    # up at 2560 and returned the STARTING width in silence, while the
    # suggestion printed afterwards searched further and named a width the
    # finder was never allowed to reach.
    check("guards", "the width finder and the suggester share one ceiling",
          B.WIDTH_CAP == 3600 and B.WIDTH_START == 1180,
          f"start {B.WIDTH_START}, cap {B.WIDTH_CAP}")
    check("guards", "a width that cannot be found comes back as None",
          B.fit_width({"out": "unused", "panels": [{
              "head": "h", "caption": "", "layout": "flow",
              "nodes": [{"id": f"n{i}", "label": "Reconciliation " * 3,
                         "col": i, "row": 0} for i in range(14)]}]}) is None,
          "it returned a width instead of admitting defeat")

    # An eight-step labelled flowchart is the case that exposed it.
    long_src = "flowchart LR\n" + "\n".join(
        f"  n{i}[Reconciliation] -->|once it has been fully approved| "
        f"n{i + 1}[Provisioning]" for i in range(8))
    imported, _g = M.to_spec(M.extract(long_src))
    if not quietly(B.validate, copy.deepcopy(imported))[0]:
        check("guards", "a long labelled import finds a width and uses it",
              build_spec(imported)[1] == 0,
              "it drew at the starting width and reported the problems")

    # Mermaid link forms that used to invent a node out of their own arrowhead.
    for form, why in (("o--o", "circle edge"), ("x--x", "cross edge")):
        _s, g = M.to_spec(M.extract(f"flowchart LR\n  A {form} B"))
        check("guards", f"a {why} link does not invent a node",
              list(g.labels) == ["A", "B"], f"got {list(g.labels)}")

    # The spaced subgraph form is the one in Mermaid's own documentation.
    _s, g = M.to_spec(M.extract(
        "flowchart TB\n  subgraph ide1 [One]\n  a-->b\n  end"))
    check("guards", "a subgraph title is read from the spaced form",
          any("'One'" in d for d in g.dropped), f"{g.dropped[:1]}")

    # An invisible link is not a thick one, and saying so states a cause the
    # code has not established.
    _s, g = M.to_spec(M.extract("flowchart LR\n  a ~~~ b"))
    check("guards", "an invisible link is not called a thick one",
          any("invisible" in d for d in g.dropped)
          and not any("thick" in d for d in g.dropped), f"{g.dropped[:1]}")

    # A direction that is not one of the five used to produce an LR layout
    # without complaint.
    try:
        M.to_spec(M.extract("flowchart LR\n  a --> b"), direction="sideways")
        check("guards", "an unknown --direction is refused", False,
              "it was accepted")
    except M.MermaidError as exc:
        check("guards", "an unknown --direction is refused",
              "SIDEWAYS" in str(exc), str(exc)[:50])

    # --png must not turn a clean run into a failed one when Playwright is
    # missing: export_png calls sys.exit() at import time.
    import preview_panels as P
    _, printed = quietly(P._png, [])
    check("guards", "--png degrades instead of aborting the run",
          "skipped" in printed or "needs" in printed or printed == "",
          f"it printed {printed[:60]!r}")

    # "#zzzzzz" starts with a hash and is not a colour. A leading hash was the
    # whole test on four of the five colour surfaces, so it went into the file
    # verbatim — while the same string in a theme was properly refused.
    surfaces = {
        "a flow node wash": {"head": "h", "caption": "", "layout": "flow",
                             "nodes": [{"id": "a", "label": "A", "col": 0,
                                        "row": 0, "wash": "#zzzzzz"}]},
        "a grid item wash": {"head": "h", "caption": "", "layout": "grid",
                             "items": [{"shape": "doc", "label": "d",
                                        "wash": "#zzzzzz"}]},
        "an icon_tint": {"head": "h", "caption": "", "layout": "grid",
                         "items": [{"icon": ["net", "Server"], "label": "s",
                                    "icon_tint": "#zzzzzz"}]},
        "a panel tint": {"head": "h", "caption": "", "layout": "row",
                         "marker": "m", "tint": "#zzzzzz",
                         "items": [{"icon": ["net", "Server"], "label": "s"}]},
        "a poster edge colour": {
            "head": "h", "caption": "", "layout": "poster",
            "items": [{"id": "a", "shape": "doc", "label": "1", "x": .3, "y": .5},
                      {"id": "b", "shape": "doc", "label": "2", "x": .7, "y": .5}],
            "edges": [{"from": "a", "to": "b", "colour": "#zzzzzz"}]},
        "a poster note colour": {
            "head": "h", "caption": "", "layout": "poster",
            "items": [{"id": "a", "shape": "doc", "label": "1", "x": .5, "y": .4}],
            "notes": [{"text": "n", "x": .5, "y": .8, "colour": "#zzzzzz"}]},
    }
    for name, panel in surfaces.items():
        errs = quietly(B.validate, {"out": "unused", "panels": [panel]})[0]
        check("guards", f"{name} that only looks like a hex is refused",
              any("#zzzzzz" in e for e in errs), f"got {errs[:1]}")
    check("guards", "and a real short hex is still accepted",
          B.is_colour("#bad") and B.is_colour("#1a2029")
          and not B.is_colour("#12345"),
          "the hex test is wrong")

    # The theme is applied before the panels are checked, so EVERY return has
    # to put it back — not only the last one.
    scene.apply_theme({"ink": "#abcdef"})
    quietly(B.validate, {"out": "unused", "theme": {"ink": "#123456"}})
    check("guards", "validating a spec with no panels leaves the theme alone",
          scene.INK == "#abcdef", f"ink became {scene.INK}")
    scene.reset_theme()

    # library._invisible's 8-digit branch was never reached.
    check("guards", "an #rrggbbaa stroke with zero alpha counts as invisible",
          lib._invisible("#11223300") and not lib._invisible("#112233ff"),
          "the 8-digit alpha branch is wrong")

    # mermaid_to_spec promises "anything dropped is reported". Nothing read it.
    dropped_cases = {
        "subgraph": ("flowchart TB\n  subgraph one [Group]\n  a-->b\n  end", "subgraph"),
        "self-link": ("flowchart LR\n  a --> a\n  a --> b", "self-link"),
        "bidirectional": ("flowchart LR\n  a <--> b", "two-headed"),
        "circle-edge link": ("flowchart LR\n  a o--o b", "two-headed"),
        "invisible link": ("flowchart LR\n  a ~~~ b", "invisible"),
        "dotted link": ("flowchart LR\n  a -.-> b", "dotted"),
        "thick link": ("flowchart LR\n  a ==> b", "thick"),
    }
    for name, (src, word) in dropped_cases.items():
        _spec, g = M.to_spec(M.extract(src))
        check("guards", f"a {name} is reported as dropped",
              any(word in d for d in g.dropped), f"reported {g.dropped[:2]}")


def coverage():
    """Colours the contrast report and the validator were not looking at."""
    # A wash on a flow node, a poster zone, a layer band or a stack row is not
    # an "item", so the item validator never sees it. An unknown name used to
    # go straight into the file as a colour.
    for group, panel in (
        ("flow node", {"head": "h", "caption": "", "layout": "flow",
                       "nodes": [{"id": "a", "label": "A", "col": 0, "row": 0,
                                  "wash": "lemonade"}]}),
        ("poster zone", {"head": "h", "caption": "", "layout": "poster",
                         "zones": [{"label": "z", "x": .1, "y": .1, "w": .5,
                                    "h": .5, "wash": "lemonade"}],
                         "items": [{"id": "i", "shape": "doc", "label": "d",
                                    "x": .5, "y": .5}]}),
        ("layers band", {"head": "h", "caption": "", "layout": "layers",
                         "bands": [{"label": "b", "wash": "lemonade",
                                    "items": [{"icon": ["net", "Server"],
                                               "label": "s"}]}]}),
        ("stack row", {"head": "h", "caption": "", "layout": "stack",
                       "rows": [{"label": "r", "wash": "lemonade"}]}),
    ):
        errs = quietly(B.validate, {"out": "unused", "panels": [panel]})[0]
        check("coverage", f"an unknown wash on a {group} is refused",
              any("lemonade" in e for e in errs), f"got {errs[:1]}")

    # A panel carries a marker tint of its own and a poster edge carries a line
    # colour. Both are drawn; neither was being measured for contrast.
    invisible = "#fffdf5"          # all but identical to the panel
    unmeasured = {
        "a panel marker tint": {"head": "h", "caption": "", "layout": "row",
                                "marker": "look here", "tint": invisible,
                                "items": [{"icon": ["net", "Server"],
                                           "label": "one"}]},
        "a poster edge colour": {
            "head": "h", "caption": "", "layout": "poster",
            "items": [{"id": "a", "shape": "doc", "label": "one", "x": .25,
                       "y": .5},
                      {"id": "b", "shape": "doc", "label": "two", "x": .75,
                       "y": .5}],
            "edges": [{"from": "a", "to": "b", "colour": invisible}]},
    }
    for name, panel in unmeasured.items():
        spec = {"out": "unused", "panels": [panel]}
        errs, _ = quietly(B.validate, spec)
        notes = quietly(B.build, copy.deepcopy(spec))[1] if not errs else ""
        check("coverage", f"{name} nobody can see earns a note",
              "note:" in notes, f"errs {errs[:1]} notes {notes[:60]!r}")

    # And the same two fields with a colour NAME rather than a hex. contrast()
    # returns None for a name it cannot parse and a None counts as a pass, so
    # only validation can refuse these — the note path proves nothing here.
    for name, panel in unmeasured.items():
        bad = json.loads(json.dumps(panel).replace(invisible, "puce"))
        errs = quietly(B.validate, {"out": "unused", "panels": [bad]})[0]
        check("coverage", f"{name} that is not a colour at all is refused",
              any("puce" in e for e in errs), f"got {errs[:1]}")

    # A label inside a washed box sits on the WASH. The wash can clear the panel
    # comfortably while swallowing the ink inside it.
    dark_wash = {"out": "unused",
                 "theme": {"palette": {"sky": "#1c1c1c"}},
                 "panels": [{"head": "h", "caption": "", "layout": "flow",
                             "nodes": [{"id": "a", "label": "A", "col": 0,
                                        "row": 0, "wash": "sky"}]}]}
    errs = quietly(B.validate, dark_wash)[0]
    check("coverage", "ink that vanishes inside its own wash is reported",
          any("wash" in e and "sky" in e for e in errs), f"got {errs[:1]}")
    scene.reset_theme()

    # The caption is drawn BELOW the frame, on the canvas.
    dark_canvas = {"out": "unused", "background": "#7d7266",
                   "panels": [{"head": "h", "caption": "a caption",
                               "layout": "flow",
                               "nodes": [{"id": "a", "label": "A", "col": 0,
                                          "row": 0}]}]}
    errs, _ = quietly(B.validate, dark_canvas)
    notes = quietly(B.build, copy.deepcopy(dark_canvas))[1] if not errs else ""
    check("coverage", "a caption invisible on its own canvas is reported",
          any("caption" in e for e in errs) or "caption" in notes,
          f"errs {errs[:1]} notes {notes[:60]!r}")
    scene.reset_theme()

    # The title is drawn on the canvas. A spec can set that canvas directly,
    # without a theme, so the title's contrast must be scored against it.
    spec = {"out": "unused", "background": "#e8590c",
            "panels": [{"head": "h", "caption": "", "layout": "flow",
                        "nodes": [{"id": "a", "label": "A", "col": 0,
                                   "row": 0}]}]}
    errs, printed = quietly(B.validate, spec)
    notes = quietly(B.build, copy.deepcopy(spec))[1] if not errs else ""
    check("coverage", "a title invisible on its own canvas is reported",
          any("title" in e for e in errs) or "note: title" in notes,
          f"errs {errs[:1]} notes {notes[:70]!r}")
    scene.reset_theme()


def gridrow():
    """A grid row holds icons of wildly different heights. They have to line up.

    The network set's firewall is 2.9x the height of its client and 17x its VPN.
    Hanging them all from a common top put one label halfway up its neighbour
    and left the connector pointing at empty space.
    """
    def board_of(items, **panel):
        spec = {"out": "unused"}
        spec["panel_h"] = panel.pop("panel_h", 780)
        spec["panels"] = [dict(
            {"head": "h", "caption": "", "layout": "grid", "cols": len(items),
             "item_size": 110, "items": items}, **panel)]
        errs = quietly(B.validate, spec)[0]
        if errs:
            return None, errs
        return build_spec(spec), None

    def icons(board):
        """Each stamped icon's (centre x, top, bottom)."""
        groups = {}
        for e in board.elements:
            for g in e.get("groupIds", []):
                groups.setdefault(g, []).append(e)
        out = []
        for els in groups.values():
            x1 = min(e["x"] for e in els)
            x2 = max(e["x"] + e.get("width", 0) for e in els)
            out.append(((x1 + x2) / 2,
                        min(e["y"] for e in els),
                        max(e["y"] + e.get("height", 0) for e in els)))
        return sorted(out)

    # The tallest icon sits in the MIDDLE on purpose. With it first, a row band
    # measured from only the first item would come out right by accident.
    ragged = [{"icon": ["net", "VPN"], "label": "short", "note": "a note"},
              {"icon": ["net", "Firewall"], "label": "tall", "note": "a note"},
              {"icon": ["net", "Router"], "label": "middling", "note": "a note"}]
    (board, problems), errs = board_of(ragged)
    if not check("grid", "a row of mismatched icons validates", not errs,
                 "; ".join(errs[:1]) if errs else ""):
        return
    check("grid", "a row of mismatched icons builds clean", problems == 0)

    labels = {e["text"]: round(e["y"], 3) for e in board.elements
              if e.get("type") == "text"}
    ys = [labels.get(k) for k in ("tall", "short", "middling")]
    check("grid", "the labels in a row share one baseline",
          None not in ys and max(ys) - min(ys) < 0.01, f"label tops {ys}")

    placed = icons(board)
    bottoms = [round(b, 2) for _cx, _t, b in placed]
    check("grid", "the icons in a row stand on one baseline",
          max(bottoms) - min(bottoms) < 1.0, f"icon bottoms {bottoms}")

    hairs = [e for e in board.elements
             if e.get("type") == "arrow" and e["strokeColor"] == scene.HAIR]
    check("grid", "a connector is drawn between each neighbouring pair",
          len(hairs) == len(ragged) - 1, f"{len(hairs)} connectors")
    for a in hairs:
        left = [i for i in placed if i[0] < a["x"]]
        right = [i for i in placed if i[0] > a["x"] + a["width"]]
        if not (left and right):
            check("grid", "a connector has an icon each side", False)
            continue
        near = (left[-1], right[0])
        check("grid", f"the connector at x={a['x']:.0f} points inside both icons",
              all(t <= a["y"] <= b for _cx, t, b in near),
              f"y {a['y']:.0f} against extents "
              f"{[(round(t), round(b)) for _c, t, b in near]}")

    # Equal heights must behave exactly as before: nothing shifted down.
    same = [{"icon": ["net", "Router"], "label": f"r{i}"} for i in range(3)]
    (board, _p), errs = board_of(same)
    tops = [round(t, 2) for _cx, t, _b in icons(board)]
    check("grid", "a row of equal icons is not shifted at all",
          not errs and max(tops) - min(tops) < 0.01, f"icon tops {tops}")

    # Two rows. The tall icon and the long note are on DIFFERENT items, so a row
    # measured as max(icon + text) reserves far too little — the note runs down
    # into the row below. Nothing catches that: the bounds check only looks at
    # the panel edge, and the collision check only compares text against text,
    # so a note landing on an ICON passes both. It has to be measured here.
    mixed = [{"icon": ["net", "Router"], "label": "wide"},
             {"icon": ["net", "Firewall"], "label": "tall"},
             {"icon": ["net", "VPN"], "label": "short",
              "note": "a note long enough to wrap over many lines and eat all "
                      "the room underneath the icon it belongs to, and then "
                      "some more besides, so the row below has nowhere to go"},
             {"icon": ["net", "Server"], "label": "s1", "note": "one"},
             {"icon": ["net", "Switch"], "label": "s2", "note": "two"},
             {"icon": ["net", "Hub"], "label": "s3", "note": "three"}]
    (board, problems), errs = board_of(mixed, cols=3, item_size=90,
                                       panel_h=900)
    if not check("grid", "a two-row grid builds clean",
                 not errs and problems == 0,
                 f"{problems} problem(s)" if not errs else errs[0]):
        return

    placed = icons(board)
    baselines = sorted({round(b, 2) for _cx, _t, b in placed})
    check("grid", "two rows of icons give two baselines", len(baselines) == 2,
          f"baselines {baselines}")
    if len(baselines) == 2:
        next_row_top = min(t for _cx, t, b in placed
                           if round(b, 2) == baselines[1])
        deepest = max((e["y"] + e.get("height", 0) for e in board.elements
                       if e.get("type") == "text"
                       and e["y"] < baselines[1] - 1), default=0)
        check("grid", "the first row's text stops above the second row",
              deepest < next_row_top,
              f"text reaches {deepest:.0f}, next row starts at "
              f"{next_row_top:.0f} — {deepest - next_row_top:.0f} over")

    hairs = [e for e in board.elements
             if e.get("type") == "arrow" and e["strokeColor"] == scene.HAIR]
    check("grid", "connectors join within a row and never across rows",
          len(hairs) == 4, f"{len(hairs)} connectors, expected 4")


def flowfit():
    """A five-step process is the commonest diagram anyone draws, and five
    columns do not fit the default panel. Every check here started as a real
    prompt that produced a broken board."""

    def board_of(nodes, edges=(), **spec_extra):
        # panel_w is pinned unless a check explicitly drops it: with no width
        # named the build finds one that fits, which would hide whether the
        # layout shrinks correctly inside a width it was given.
        spec = dict({"out": "unused", "panel_w": 1180}, **spec_extra)
        if spec.get("panel_w") is None:
            spec.pop("panel_w")
        spec["panels"] = [{"head": "h", "caption": "", "layout": "flow",
                           "nodes": nodes, "edges": list(edges)}]
        errs = quietly(B.validate, spec)[0]
        if errs:
            return None, 0, "; ".join(errs[:1]), spec
        (board, problems), printed = quietly(B.build, copy.deepcopy(spec))
        return board, problems, printed, spec

    def bursting(board):
        """Node labels wider than the box drawn around them.

        Neither shipped check can see this: the text is inside the panel, so
        bounds passes, and it only touches its own box, so collisions passes.
        It still looks broken — the word crosses the outline on both sides.
        """
        bad, pending = [], None
        for e in board.elements:
            if e.get("type") == "rectangle" and e["id"].startswith("n"):
                pending = e
            elif e.get("type") == "text" and pending is not None:
                if e["width"] > pending["width"] + 1:
                    bad.append((e.get("text"), round(e["width"]),
                                round(pending["width"])))
                pending = None
        return bad


    steps = ["Enquiry", "Discovery call", "Proposal", "Deposit", "Kickoff"]
    nodes = [{"id": f"n{i}", "label": s, "col": i, "row": 0}
             for i, s in enumerate(steps)]
    edges = [[f"n{i}", f"n{i+1}"] for i in range(4)]
    board, problems, printed, spec = board_of(nodes, edges)
    check("flowfit", "five plain steps fit the default panel",
          board is not None and problems == 0, printed)

    # An unbreakable word is the thing a column cannot shrink under.
    long_words = ["Onboarding", "Underwriting", "Completion", "Reconciliation",
                  "Provisioning"]
    nodes = [{"id": f"n{i}", "label": s, "col": i, "row": 0}
             for i, s in enumerate(long_words)]
    # Each column has to be at least as wide as its own longest word. Drop that
    # floor and the panel is divided evenly instead, which looks fine to the
    # bounds check while "Reconciliation" crosses the outline of its own box.
    board, problems, printed, spec = board_of(nodes, panel_w=None)
    if check("flowfit", "five one-word steps validate", board is not None,
             printed):
        check("flowfit", "a long single word stays inside the panel",
              not outside(board, spec), f"{outside(board, spec)[:2]}")
        check("flowfit", "and inside its own box",
              not bursting(board), f"{bursting(board)[:2]}")
        check("flowfit", "and the panel comes out clean", problems == 0, printed)

    # A note under the first or last column is centred on a box already against
    # the margin, so it needs clamping like every other layout's lettering.
    nodes = [{"id": "a", "label": "Start", "col": 0, "row": 0,
              "note": "a soft check that is not binding on anyone at all"},
             {"id": "b", "label": "Middle", "col": 1, "row": 0},
             {"id": "c", "label": "End", "col": 2, "row": 0,
              "note": "this one is legally binding from here onwards"}]
    board, problems, printed, spec = board_of(nodes, [["a", "b"], ["b", "c"]])
    if check("flowfit", "notes on the edge columns validate", board is not None,
             printed):
        check("flowfit", "a note on an edge column stays inside the panel",
              not outside(board, spec), f"{outside(board, spec)[:2]}")

    # Five rows overflow the default height unless the row gaps close up.
    nodes = [{"id": f"r{i}", "label": f"Step {i}", "col": 0, "row": i}
             for i in range(5)]
    board, problems, printed, spec = board_of(
        nodes, [[f"r{i}", f"r{i+1}"] for i in range(4)])
    check("flowfit", "five stacked rows fit the default panel",
          board is not None and problems == 0, printed)

    # Four columns and three arrow labels fit 1180 only because the labels are
    # re-wrapped to the gap they ended up with. Wrap them to a fixed width and
    # two of them land on the box beside them.
    four = [{"id": f"n{i}", "label": l, "col": i, "row": 0} for i, l in
            enumerate(["Enquiry", "Discovery call", "Proposal", "Kickoff"])]
    board, problems, printed, spec = board_of(
        four, [["n0", "n1", "if it fits"], ["n1", "n2", "once approved"],
               ["n2", "n3", "on signature"]])
    check("flowfit", "arrow labels are re-wrapped to the gap they get",
          board is not None and problems == 0, printed)

    # Pinned too narrow on purpose. The panel overflows and says so, but even
    # then a box must still hold its own label: the last-resort scale shrinks
    # the columns and has to stop at the floor like every other step does.
    cramped = [{"id": f"n{i}", "label": s, "col": i, "row": 0}
               for i, s in enumerate(long_words)]
    board, problems, printed, spec = board_of(cramped, panel_w=1180)
    if check("flowfit", "a flow pinned too narrow still builds", board is not None,
             printed):
        check("flowfit", "it overflows the panel and says which width works",
              problems > 0 and "draws clean" in printed, printed[:80])
        check("flowfit", "but no box is left narrower than its own label",
              not bursting(board), f"{bursting(board)[:2]}")

    # A note is centred on its box. Under column 0 that box is already against
    # the margin, so without a clamp the note hangs outside the frame.
    noted = [{"id": f"n{i}", "label": l, "col": i, "row": 0} for i, l in
             enumerate(["Agreement", "Application", "Valuation",
                        "Underwriting", "Formal offer"])]
    noted[0]["note"] = ("a soft check that is not binding on anyone and is "
                        "only indicative")
    board, problems, printed, spec = board_of(
        noted, [[f"n{i}", f"n{i+1}"] for i in range(4)], panel_w=1220)
    if check("flowfit", "a five-column flow with a note validates",
             board is not None, printed):
        check("flowfit", "a note under the first column is clamped inside",
              not outside(board, spec) and problems == 0,
              f"{outside(board, spec)[:2]}")

    # Five steps AND three labelled arrows genuinely need more than 1180. With
    # no width named, the build is expected to go and find one.
    nodes = [{"id": f"n{i}", "label": s, "col": i, "row": 0}
             for i, s in enumerate(steps)]
    edges = [["n0", "n1", "if it fits"], ["n1", "n2", "once approved"],
             ["n2", "n3", "on signature"], ["n3", "n4"]]
    board, problems, printed, spec = board_of(nodes, edges, panel_w=None)
    check("flowfit", "a flow too wide for the default is widened, not broken",
          board is not None and problems == 0, printed)
    check("flowfit", "and it says out loud that it widened it",
          "widened the panel" in printed, printed[:80])

    # A width the author DID name is theirs. Respect it, and report one that
    # works rather than quietly overriding them.
    wide = [{"id": "a", "label": "Agreement in principle", "col": 0, "row": 1},
            {"id": "b", "label": "Full application", "col": 1, "row": 1},
            {"id": "c", "label": "Valuation", "col": 2, "row": 1},
            {"id": "d", "label": "Underwriting", "col": 3, "row": 1},
            {"id": "e", "label": "Formal offer", "col": 4, "row": 1},
            {"id": "x", "label": "Declined", "col": 3, "row": 0}]
    wedges = [["a", "b"], ["b", "c"], ["c", "d"], ["d", "e", "approved"],
              ["d", "x", "affordability"]]
    board, problems, printed, spec = board_of(wide, wedges, panel_w=None)
    check("flowfit", "the same flow with no width named comes out clean",
          board is not None and problems == 0, printed)

    board, problems, printed, spec = board_of(wide, wedges)
    if not check("flowfit", "a narrow panel_w the author chose is respected",
                 board is not None and problems > 0,
                 "it overrode a width the spec asked for"):
        return
    offered = re.search(r'"panel_w": (\d+)', printed)
    if not check("flowfit", "it offers a panel_w that would work", offered,
                 printed[:90]):
        return
    retry = copy.deepcopy(spec)
    retry["panel_w"] = int(offered.group(1))
    check("flowfit", f"the offered panel_w ({offered.group(1)}) really works",
          quietly(B.build, retry)[0][1] == 0,
          "the number it printed does not actually draw clean")


def preview():
    """A preview panel has to BE the panel, not a lookalike rebuilt differently."""
    import preview_panels as P
    spec = spec_or_skip("preview", "layouts-tour.json")
    if spec is None:
        return
    pw = spec.get("panel_w", 1180)
    gap = spec.get("gap", 300)
    full = build_spec(spec)[0].elements

    # The build emits, per panel: title, frame{i}, body…, cap{i}, then flow{i}.
    starts = [i for i, e in enumerate(full) if e["id"].startswith("frame")]
    groups = []
    for k, s in enumerate(starts):
        end = starts[k + 1] - 1 if k + 1 < len(starts) else len(full)
        groups.append([e for e in full[s - 1:end]
                       if not e["id"].startswith("flow")])

    def shape(e, dx):
        return (e["type"], round(e["x"] - dx, 3), round(e["y"], 3),
                round(e.get("width", 0), 3), round(e.get("height", 0), 3),
                e.get("text"), e["strokeColor"], e["backgroundColor"],
                e.get("fontSize"),
                tuple(tuple(round(v, 3) for v in p)
                      for p in (e.get("points") or [])))

    for n, panel in enumerate(spec["panels"], 1):
        sub = {k: spec[k] for k in P.CARRIED if k in spec}
        sub["panels"] = [panel]
        sub["out"] = "unused"
        one = build_spec(sub)[0].elements
        dx = 120 + (n - 1) * (pw + gap)
        check("preview", f"panel {n} matches the full board",
              [shape(e, dx) for e in groups[n - 1]] ==
              [shape(e, 120) for e in one])

    # A spec that names no width is the case that breaks: the board settles one
    # width for every panel, and a preview left to choose for itself would pick
    # a narrower one. layouts-tour pins its width, so nothing here covered it.
    unpinned = {"out": "unused", "panels": [
        {"head": "wide", "caption": "", "layout": "flow",
         "nodes": [{"id": f"w{i}", "label": l, "col": i, "row": 0} for i, l in
                   enumerate(["Reconciliation", "Provisioning", "Onboarding",
                              "Underwriting", "Completion"])]},
        {"head": "narrow", "caption": "", "layout": "flow",
         "nodes": [{"id": "a", "label": "One", "col": 0, "row": 0},
                   {"id": "b", "label": "Two", "col": 1, "row": 0}],
         "edges": [["a", "b"]]}]}
    whole = B.fit_width(copy.deepcopy(unpinned))
    alone = B.fit_width({"out": "unused", "panels": [unpinned["panels"][1]]})
    if check("preview", "the two panels want different widths on their own",
             whole != alone, f"both want {whole}, so this proves nothing"):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "unpinned.json"
            path.write_text(json.dumps(unpinned))
            quietly(P.preview, path, out_dir=tmp)
            widths = []
            for f in sorted(pathlib.Path(tmp).glob("panel-*.excalidraw")):
                els = json.loads(f.read_text())["elements"]
                frame = next(e for e in els if e["id"].startswith("frame"))
                widths.append(round(frame["width"]))
            check("preview", "every preview panel uses the board's width",
                  widths and set(widths) == {whole},
                  f"previews came out {widths}, board is {whole}")

    # When no width fits, fit_width returns None and build() draws at the
    # starting width. A preview that left the key absent instead let each panel
    # choose for itself, and showed a panel the board does not contain.
    unfittable = {"out": "unused", "panels": [
        {"head": "impossible", "caption": "", "layout": "flow",
         "nodes": [{"id": f"u{i}", "label": "Reconciliation Reconciliation",
                    "col": i, "row": 0} for i in range(14)]},
        # Wants MORE than the starting width on its own, so a preview that
        # picks per-panel comes out different from the board.
        {"head": "roomy", "caption": "", "layout": "flow",
         "nodes": [{"id": f"r{i}", "label": l, "col": i, "row": 0} for i, l in
                   enumerate(["Enquiry", "Discovery call", "Proposal",
                              "Deposit", "Kickoff"])],
         "edges": [["r0", "r1", "if it fits"], ["r1", "r2", "once approved"],
                   ["r2", "r3", "on signature"]]}]}
    if check("preview", "the awkward fixture really has no width that fits",
             B.fit_width(copy.deepcopy(unfittable)) is None,
             "a width was found, so this proves nothing"):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "unfittable.json"
            path.write_text(json.dumps(unfittable))
            quietly(P.preview, path, out_dir=tmp)
            widths = []
            for f in sorted(pathlib.Path(tmp).glob("panel-*.excalidraw")):
                els = json.loads(f.read_text())["elements"]
                widths.append(round(next(e for e in els
                                         if e["id"].startswith("frame"))["width"]))
            check("preview", "and every panel still uses the board's width",
                  widths and set(widths) == {B.WIDTH_START},
                  f"previews came out {widths}, board draws at {B.WIDTH_START}")

    # outside() is relied on by several checks, and it carried the same
    # negative-extent bug that was fixed in check_bounds.
    from excalidraw_kit import arrow as _arr
    probe = build_spec({"out": "unused", "panel_w": 1180, "panels": [{
        "head": "h", "caption": "", "layout": "flow",
        "nodes": [{"id": "a", "label": "A", "col": 0, "row": 0}]}]})[0]
    probe.elements.append(_arr("leftward", 300, 400, -400, 0))
    check("preview", "outside() sees an arrow that points off to the left",
          any(e[0] == "leftward" for e in outside(probe)),
          "the helper still reads the wrong end")

    check("preview", "the panel filename is safe to write",
          P.slug("row — a source, feeding/several") ==
          "row-a-source-feeding-several",
          P.slug("row — a source, feeding/several"))


def tint():
    entry = lib.find_item("dwelle/network-topology-icons.excalidrawlib", "Server")
    if not check("tint", "the network Server icon is available", entry):
        return
    els, _ = lib.stamp(entry, 0, 0, target_w=100, uid="t", tint="#ff0000")
    pairs = set(zip((e["strokeColor"] for e in entry["elements"]),
                    (e["strokeColor"] for e in els)))
    check("tint", "visible lines are recoloured", ("#495057", "#ff0000") in pairs)
    check("tint", "an invisible bounding box is left alone",
          ("#0000", "#0000") in pairs,
          "tinting it would draw a box the icon never had")
    check("tint", "an ink name resolves", scene.stroke_colour("red") == "#e03131")
    check("tint", "a hex passes through", scene.stroke_colour("#123456") == "#123456")
    check("tint", "nothing means nothing", scene.stroke_colour(None) is None)

    # Three layouts stamp icons by three different routes. A tint wired into one
    # of them is not wired into the skill.
    icon = ["net", "Server"]
    routes = {
        "grid": {"layout": "grid", "items": [
            {"icon": icon, "label": "s", "icon_tint": "#ff00ff"}]},
        "layers": {"layout": "layers", "bands": [
            {"label": "tier", "items": [
                {"icon": icon, "label": "s", "icon_tint": "#ff00ff"}]}]},
        "poster": {"layout": "poster", "items": [
            {"id": "s", "icon": icon, "label": "s", "x": 0.5, "y": 0.4,
             "icon_tint": "#ff00ff"}]},
    }
    for name, panel in routes.items():
        spec = {"out": "unused", "panels": [
            dict(panel, head="h", caption="")]}
        errs = quietly(B.validate, spec)[0]
        if not check("tint", f"the {name} tint spec validates", not errs,
                     "; ".join(errs[:1])):
            continue
        board = build_spec(spec)[0]
        check("tint", f"{name} passes the tint through to the icon",
              any(e["strokeColor"] == "#ff00ff" for e in board.elements),
              "the icon was stamped in its original grey")


# -------------------------------------------------------------------- checks

def colour():
    """Every colour check, proven by breaking the thing it guards."""
    base = spec_or_skip("colour", "theme-demo.json")
    if base is None:
        return

    def fires(name, mutate, expect):
        spec = copy.deepcopy(base)
        mutate(spec)
        errs, printed = quietly(B.validate, spec)
        notes = []
        if not errs:
            notes = [ln.strip() for ln in quietly(B.build, spec)[1].splitlines()
                     if ln.strip().startswith("note:")]
        got = errs + notes
        hit = (not got) if expect is None else any(expect in g for g in got)
        check("colour", name, hit, f"got {got[:1]}")

    fires("lettering nobody can see fails the build",
          lambda s: s["theme"].update(ink="#1c2029"), "will not be visible")
    fires("a wash nobody can see earns a note",
          lambda s: s["theme"]["palette"].update(sky="#1a2029"), "note: wash 'sky'")
    fires("a line colour nobody can read earns a note",
          lambda s: s["theme"]["inks"].update(blue="#26303c"),
          "note: icon_tint 'blue'")
    fires("a typo in a theme key is named",
          lambda s: s["theme"].update(backgrnd="#000000"), "unknown key")
    fires("a theme colour that is not a hex is refused",
          lambda s: s["theme"].update(ink="darkgrey"), "must be a #hex")
    fires("a palette entry that is not a hex is refused",
          lambda s: s["theme"]["palette"].update(mint="green"), "palette.mint")
    fires("a theme of the wrong type is refused",
          lambda s: s.update(theme="dark"), "must be an object")
    fires("an unknown icon_tint lists the real ones",
          lambda s: s["panels"][1]["items"][0].update(icon_tint="chartreuse"),
          "unknown icon_tint")
    fires("icon_tint on a drawn shape is refused",
          lambda s: s["panels"][1]["items"].append(
              {"shape": "doc", "label": "a file", "icon_tint": "blue"}),
          "recolours a library icon")
    fires("the shipped theme demo is itself clean", lambda s: None, None)


def specerr():
    """The spec validator, proven the same way."""
    good = {"out": "x.excalidraw", "panels": [{
        "head": "h", "caption": "c", "layout": "flow",
        "nodes": [{"id": "a", "label": "A", "col": 0, "row": 0}],
        "edges": []}]}

    def refused(name, mutate, expect):
        spec = copy.deepcopy(good)
        mutate(spec)
        errs = quietly(B.validate, spec)[0]
        check("specerr", name, any(expect in e for e in errs), f"got {errs[:1]}")

    refused("no out", lambda s: s.pop("out"), 'missing "out"')
    refused("no panels", lambda s: s.update(panels=[]), 'missing "panels"')
    refused("no head", lambda s: s["panels"][0].pop("head"), 'missing "head"')
    refused("no caption", lambda s: s["panels"][0].pop("caption"),
            'missing "caption"')
    refused("no layout", lambda s: s["panels"][0].pop("layout"),
            'missing "layout"')
    refused("unknown layout", lambda s: s["panels"][0].update(layout="spiral"),
            "unknown layout")
    refused("layout missing its content",
            lambda s: s["panels"][0].pop("nodes"), 'needs "nodes"')
    refused("flow node with no id",
            lambda s: s["panels"][0]["nodes"].append({"label": "B"}),
            'needs an "id"')
    refused("flow node with no label",
            lambda s: s["panels"][0]["nodes"].append({"id": "b"}),
            'needs a "label"')
    refused("edge to a node that is not there",
            lambda s: s["panels"][0]["edges"].append(["a", "ghost"]),
            "unknown node")
    refused("unknown shape", lambda s: s["panels"][0].update(
        layout="grid", items=[{"shape": "sausage", "label": "x"}]),
        "unknown shape")
    refused("unknown icon library", lambda s: s["panels"][0].update(
        layout="grid", items=[{"icon": ["nope", "Server"], "label": "x"}]),
        "unknown library")
    refused("icon that is not in the library", lambda s: s["panels"][0].update(
        layout="grid", items=[{"icon": ["net", "Toaster"], "label": "x"}]),
        "not found in net")
    refused("icon written the wrong way", lambda s: s["panels"][0].update(
        layout="grid", items=[{"icon": "net/Server", "label": "x"}]),
        "must be [library, item-name]")
    refused("item that is neither shape nor icon", lambda s: s["panels"][0].update(
        layout="grid", items=[{"label": "x"}]),
        'neither "shape" nor "icon"')
    refused("unknown wash", lambda s: s["panels"][0].update(
        layout="grid", items=[{"shape": "doc", "label": "x", "wash": "puce"}]),
        "unknown colour")


# ------------------------------------------------------------------- mermaid

CORPUS = {
    "pipe labels and a fan-out": ("""flowchart TD
        A[Christmas] -->|Get money| B(Go shopping)
        B --> C{Let me think}
        C -->|One| D[Laptop]
        C -->|Two| E[iPhone]
        C -->|Three| F[fa:fa-car Car]""", 6, 5, 3, 4),
    "a chain written on one line": ("""graph LR
        client --> lb --> app --> db
        app --> cache""", 5, 4, 4, 2),
    "labels written the long way": ("""flowchart LR
        A -- calls --> B
        B == bulk ==> C
        C -. async .-> D
        D --- E""", 5, 4, 5, 1),
    "every node shape": ("""flowchart TD
        a[rect] --> b(round) --> c([stadium]) --> d[[sub]] --> e[(db)]
        f((circle)) --> g>flag] --> h{choice} --> i{{hex}} --> j[/para/]""",
                         10, 8, 2, 5),
    "the ampersand fan-out": ("""flowchart LR
        A & B --> C & D
        C --> E""", 5, 5, 3, 2),
    "subgraphs are flattened": ("""flowchart TB
        c1-->a2
        subgraph ide1 [One]
        a1-->a2
        end
        a2 --> b1""", 4, 3, 2, 3),
    "quotes protect brackets and comments": (
        '''flowchart LR
        A["a label with ] and %% inside"] --> B(foo (bar))
        B --> C["Tom & Jerry"]''', 3, 2, 3, 1),
    "semicolons end statements": ("""graph TD;
        A-->B; A-->C; B-->D; C-->D;""", 4, 4, 2, 3),
    "a cycle still ranks": ("""flowchart LR
        A --> B --> C --> A""", 3, 3, 3, 1),
    "styling lines are skipped": ("""flowchart TD
        %% a comment
        A:::big --> B --> C
        classDef big fill:#f9f
        class A big
        style B fill:#bbf
        linkStyle 0 stroke:#ff3
        click A "https://example.com" """, 3, 2, 1, 3),
    "an init directive is skipped": ("""%%{init: {'theme':'forest'}}%%
        graph BT
        a --> b --> c""", 3, 2, 1, 3),
    "hyphens inside ids survive": ("""flowchart LR
        api-gw-->auth-svc-->user-db""", 3, 2, 3, 1),
    "a line break becomes a space": ("""flowchart LR
        A["line one<br/>line two"] --> B[plain]""", 2, 1, 2, 1),
    "one node on its own": ("flowchart TD\n  only[Just one box]", 1, 0, 1, 1),
    # A label on a vertical edge is pushed sideways by half its own width. In
    # the leftmost column that runs off the panel unless the gap holds it, so
    # this one fails the bounds check if panel_size stops accounting for it.
    "a long label on a vertical edge in the first column": ("""flowchart TD
        a1 -- forwards the authenticated request onward --> b1
        a2 --> b2
        a3 --> b3
        a4 --> b4""", 8, 4, 4, 2),
}

# Counts say nothing about WHERE a node landed, and a flowchart that puts every
# rank hard against one edge still counts correctly. (col, row) per node.
POSITIONS = {
    "a parent sits over its children": ("""flowchart TD
        A --> B --> C
        C --> D
        C --> E
        C --> F""",
        {"A": (1, 0), "B": (1, 1), "C": (1, 2),
         "D": (0, 3), "E": (1, 3), "F": (2, 3)}),
    "a wide fan-out centres its root": ("""flowchart TD
        root --> a1 & a2 & a3 & a4 & a5""",
        {"root": (2, 0), "a1": (0, 1), "a3": (2, 1), "a5": (4, 1)}),
    "left to right runs along the columns": ("""flowchart LR
        a --> b --> c""", {"a": (0, 0), "b": (1, 0), "c": (2, 0)}),
    "right to left runs the other way": ("""flowchart RL
        a --> b --> c""", {"a": (2, 0), "b": (1, 0), "c": (0, 0)}),
    "bottom to top climbs": ("""flowchart BT
        a --> b --> c""", {"a": (0, 2), "b": (0, 1), "c": (0, 0)}),
    # x is written first but hangs off the right-hand parent. Ordering by the
    # order of writing crosses the two edges over each other.
    "a child follows its parent, not the order it was written": ("""flowchart TD
        top --> L
        top --> R
        R --> x
        L --> y""",
        {"top": (0, 0), "L": (0, 1), "R": (1, 1), "y": (0, 2), "x": (1, 2)}),
    "a rank of two centres against a rank of three": ("""flowchart TD
        r --> x & y
        x --> p & q
        y --> s""", {"r": (1, 0), "x": (0, 1), "y": (1, 1),
                     "p": (0, 2), "q": (1, 2), "s": (2, 2)}),
}

# Counts prove the shape survived; these prove the WORDS did. Every one is a
# case where a naive parser silently keeps the wrong text.
LABELS = {
    'flowchart LR\n  A["a label with ] and %% inside"] --> B[x]':
        ("A", "a label with ] and %% inside"),
    "flowchart LR\n  A(foo (bar)) --> B[x]": ("A", "foo (bar)"),
    'flowchart LR\n  A["Tom & Jerry"] --> B[x]': ("A", "Tom & Jerry"),
    'flowchart LR\n  A["line one<br/>line two"] --> B[x]':
        ("A", "line one line two"),
    "flowchart LR\n  A[fa:fa-car Car] --> B[x]": ("A", "Car"),
    "flowchart LR\n  A[[deploy]] --> B[x]": ("A", "deploy"),
    "flowchart LR\n  A[(user table)] --> B[x]": ("A", "user table"),
    "flowchart LR\n  A(((core))) --> B[x]": ("A", "core"),
    "flowchart LR\n  A{{maybe}} --> B[x]": ("A", "maybe"),
    "flowchart LR\n  A[/tilted/] --> B[x]": ("A", "tilted"),
    "flowchart LR\n  A[\\other/] --> B[x]": ("A", "other"),
    "flowchart LR\n  A>flag] --> B[x]": ("A", "flag"),
    "flowchart LR\n  bare --> B[x]": ("bare", "bare"),
    "flowchart LR\n  A:::warn --> B[x]": ("A", "A"),
    "flowchart LR\n  A -- one & two --> B[x]": ("A", "A"),
}

EDGE_LABELS = {
    "flowchart LR\n  A -->|then| B": "then",
    "flowchart LR\n  A --> |spaced| B": "spaced",
    "flowchart LR\n  A -- calls out --> B": "calls out",
    "flowchart LR\n  A == in bulk ==> B": "in bulk",
    "flowchart LR\n  A -. later .-> B": "later",
    'flowchart LR\n  A -->|"a | is fine"| B': "a | is fine",
}

REFUSALS = {
    "sequenceDiagram\n  Alice->>John: Hi": "sequence diagram",
    "classDiagram\n  Animal <|-- Duck": "class diagram",
    "stateDiagram-v2\n  [*] --> Still": "state diagram",
    "gantt\n  title A": "Gantt chart",
    "pie title Pets\n  \"Dogs\" : 386": "pie chart",
    "%% only a comment\n": "empty once comments are removed",
    "this is not mermaid\n": "expected 'flowchart' or 'graph'",
    "flowchart TD\n": "declares no nodes",
    # The expected word must not appear in the input, or the matcher passes on
    # the parser echoing the user's own text back in a different error.
    "flowchart TD\n  A[oops --> B": "unclosed",
    "flowchart TD\n  --> B": "nothing before it",
    "flowchart TD\n  A -->": "nothing after it",
}


def mermaid():
    for name, (src, nodes, edges, cols, rows) in CORPUS.items():
        try:
            spec, _g = M.to_spec(M.extract(src))
        except M.MermaidError as exc:
            check("mermaid", name, False, f"refused: {exc}")
            continue
        p = spec["panels"][0]
        got = (len(p["nodes"]), len(p["edges"]),
               max(n["col"] for n in p["nodes"]) + 1,
               max(n["row"] for n in p["nodes"]) + 1)
        if not check("mermaid", name, got == (nodes, edges, cols, rows),
                     f"nodes/edges/cols/rows {got} != {(nodes, edges, cols, rows)}"):
            continue
        cells = {(n["row"], n["col"]) for n in p["nodes"]}
        check("mermaid", f"{name}: no two nodes share a cell",
              len(cells) == len(p["nodes"]))
        errs = quietly(B.validate, spec)[0]
        if not check("mermaid", f"{name}: the spec validates", not errs,
                     "; ".join(errs[:1])):
            continue
        problems = build_spec(spec)[1]
        check("mermaid", f"{name}: builds clean", problems == 0,
              f"{problems} bounds/collision problem(s)")


def mermaidplace():
    for name, (src, want) in POSITIONS.items():
        spec, _g = M.to_spec(M.extract(src))
        at = {n["id"]: (n["col"], n["row"]) for n in spec["panels"][0]["nodes"]}
        wrong = {k: (at.get(k), v) for k, v in want.items() if at.get(k) != v}
        check("mermaidplace", name, not wrong, f"got/wanted {wrong}")


def mermaidtext():
    for src, (nid, want) in LABELS.items():
        spec, _g = M.to_spec(M.extract(src))
        got = next((n["label"] for n in spec["panels"][0]["nodes"]
                    if n["id"] == nid), None)
        check("mermaidtext", f"{src.splitlines()[1].strip()[:34]}",
              got == want, f"read {got!r}, wanted {want!r}")
    for src, want in EDGE_LABELS.items():
        name = f"edge label {src.splitlines()[1].strip()[:26]}"
        try:
            spec, _g = M.to_spec(M.extract(src))
        except M.MermaidError as exc:
            check("mermaidtext", name, False, f"refused it: {exc}")
            continue
        edges = spec["panels"][0]["edges"]
        got = edges[0][2] if edges and len(edges[0]) > 2 else None
        check("mermaidtext", name, got == want, f"read {got!r}, wanted {want!r}")


def mermaiderr():
    for src, expect in REFUSALS.items():
        # Named by what it refuses. Four fixtures begin "flowchart TD", so
        # naming them by their first line left a failure identifying none.
        first = f"{src.splitlines()[0][:20]} / {expect[:24]}"
        try:
            M.to_spec(M.extract(src))
            check("mermaiderr", first, False, "it was accepted")
        except M.MermaidError as exc:
            check("mermaiderr", first, expect in str(exc), f"said {exc}")
        except Exception as exc:                       # noqa: BLE001
            check("mermaiderr", first, False,
                  f"{type(exc).__name__} instead of a plain message: {exc}")


def main():
    for group in (specs, determinism, theme, themereach, guards, coverage,
                  gridrow,
                  flowfit, preview, tint, colour, specerr,
                  mermaid, mermaidplace, mermaidtext, mermaiderr):
        try:
            group()
        except Exception as exc:                       # noqa: BLE001
            # A group that throws still has to report, or one exception hides
            # every check after it and the run looks like a crash, not a result.
            check(group.__name__, "the group ran to the end", False,
                  f"{type(exc).__name__}: {exc}")
    print()
    width = max(len(g) for g, *_ in RESULTS)
    for name in dict.fromkeys(g for g, *_ in RESULTS):
        rows = [r for r in RESULTS if r[0] == name]
        passed = sum(1 for r in rows if r[2])
        print(f"  {name:{width}}  {passed}/{len(rows)}"
              f"{'' if passed == len(rows) else '   <-- FAILURES'}")
    failed = [r for r in RESULTS if not r[2]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
