#!/usr/bin/env python3
"""Scene primitives and layout engines for library-built boards.

Everything here used to live inside one topic-specific build script, which meant
the next board started from nothing. A panel is now *described* — a layout name
and a list of items — and placed by code that knows the panel's bounds.

An item is either a **shape** (drawn from primitives here) or an **icon**
(stamped from a community library):

    {"shape": "doc",   "label": "policy file", "wash": "lilac"}
    {"icon": ["net", "Server"], "label": "server", "wash": "sky"}

plus optional `marker` (hand-lettered label on a highlighter swipe — the "area
of focus") which replaces `label` when present.

Layouts: hub, row, grid, pair. Each returns nothing and draws into the board;
all of them keep content inside the panel rect they are handed.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from excalidraw_kit import txt, rect, ellipse, arrow, line, measure  # noqa: E402
import library as lib                                                # noqa: E402

INK = "#1e1e1e"
MUTED = "#7d7266"
# What an acronym stands for, set apart from the plain-English note.
FULL_C = "#9c6644"
FULL_SIZE = 15
FULL_SIZE_BAND = 12
PANEL_BG = "#fffdf6"

PALETTE = {
    "mint": "#c3fae8", "lilac": "#e9d8fd", "sky": "#d0ebff",
    "peach": "#ffd8a8", "rose": "#ffc9c9", "lemon": "#fff3bf",
    "none": "transparent",
}

LIBS = {
    "net": "dwelle/network-topology-icons.excalidrawlib",
    "people": "dhtoran/stick-people.excalidrawlib",
    "logos": "pclainchard/it-logos.excalidrawlib",
    "office": "m47812/office-items.excalidrawlib",
    "elements": "samu_x86/network-elements.excalidrawlib",
    # 249 named AWS service icons — the only AWS library whose items are named
    # rather than item-0..item-N, which is what makes it usable from a spec.
    "aws": "childishgirl/aws-architecture-icons.excalidrawlib",
    # GCP: 139 named icons, one library covers the whole platform.
    "gcp": "mguidoti/original-google-architecture-icons.excalidrawlib",
    # Azure has no single good library — the core set is spread over six, so a
    # spec picks the right one per icon.
    "az":     "youritjang/azure-cloud-services.excalidrawlib",
    "azdata": "rockssk/microsoft-azure-cloud-icons.excalidrawlib",
    "azc":    "7demonsrising/azure-compute.excalidrawlib",
    "azn":    "7demonsrising/azure-network.excalidrawlib",
    "azs":    "7demonsrising/azure-storage.excalidrawlib",
    "azg":    "7demonsrising/azure-general.excalidrawlib",
    "azk":    "7demonsrising/azure-containers.excalidrawlib",
    "azm":    "ubigene/misc-azure-icons.excalidrawlib",
    # Non-cloud sets that carry business and process diagrams.
    "orgchart": "jgodoy/organization-chart.excalidrawlib",
    "figures":  "youritjang/stick-figures.excalidrawlib",
    "parts":    "rochacbruno/computer-parts.excalidrawlib",
}

# Libraries that bake a caption into every icon. Their text is stripped so the
# spec's own label is the only one — and is right.
STRIP_TEXT = {"aws", "gcp", "az", "azdata", "azc", "azn", "azs",
              "azg", "azk", "azm",
              # org-chart items ship placeholder text ("Person Name") that
              # would otherwise print on the board next to your own label
              "orgchart"}

# height / width for each primitive, so a layout can reserve space before drawing
SHAPE_RATIO = {"doc": 1.25, "padlock": 1.12, "tag": 0.60, "clipboard": 1.25,
               "door": 1.58, "cloud": 0.48, "ring": 1.00, "range": 0.58}

_n = [0]


def uid(p="e"):
    _n[0] += 1
    return f"{p}{_n[0]}"


def colour(name):
    return PALETTE.get(name, name or "transparent")


# ---------------------------------------------------------------- primitives

def doc(b, cx, top, w):
    h = w * SHAPE_RATIO["doc"]
    b.add(rect(uid("d"), cx - w / 2, top, w, h, stroke=INK,
               bg=PALETTE["lilac"], radius=False))
    b.add(line(uid("d"), cx + w / 2 - w * .22, top, w * .22, 0, INK))
    b.add(line(uid("d"), cx + w / 2 - w * .22, top, 0, w * .22, INK))
    for i in range(5):
        b.add(line(uid("d"), cx - w / 2 + w * .15, top + h * .26 + i * h * .135,
                   w * .62, 0, "#6b46c1"))
    return w, h


def padlock(b, cx, top, w):
    # Shackle first, body second — otherwise the two overlap into a handbag.
    b.add(ellipse(uid("p"), cx - w * .29, top, w * .58, w * .62,
                  stroke=INK, bg="transparent"))
    b.add(rect(uid("p"), cx - w / 2, top + w * .40, w, w * .70, stroke=INK,
               bg=PALETTE["peach"], radius=True))
    b.add(ellipse(uid("p"), cx - w * .09, top + w * .68, w * .18, w * .18,
                  stroke=INK, bg=INK))
    return w, w * SHAPE_RATIO["padlock"]


def tag(b, cx, top, w):
    h = w * SHAPE_RATIO["tag"]
    b.add(rect(uid("g"), cx - w / 2, top, w, h, stroke=INK,
               bg=PALETTE["peach"], radius=True))
    b.add(ellipse(uid("g"), cx + w / 2 - w * .23, top + h / 2 - w * .06,
                  w * .12, w * .12, stroke=INK, bg=PANEL_BG))
    b.add(line(uid("g"), cx + w / 2 - w * .04, top + h / 2 - w * .04,
               w * .23, -w * .15, INK))
    return w, h


def clipboard(b, cx, top, w):
    h = w * SHAPE_RATIO["clipboard"]
    x = cx - w / 2
    b.add(rect(uid("c"), x, top, w, h, stroke=INK, bg=PALETTE["mint"],
               radius=True))
    b.add(rect(uid("c"), cx - w * .15, top - h * .07, w * .30, h * .11,
               stroke=INK, bg=PALETTE["mint"], radius=True))
    for i in range(4):
        ry = top + h * .19 + i * h * .20
        b.add(line(uid("c"), x + w * .12, ry + h * .047, w * .48, 0, INK))
        if i < 3:
            b.add(line(uid("c"), x + w * .68, ry + h * .04, w * .05, h * .05,
                       "#2f9e44"))
            b.add(line(uid("c"), x + w * .73, ry + h * .09, w * .10, -h * .10,
                       "#2f9e44"))
        else:
            b.add(line(uid("c"), x + w * .68, ry, w * .11, h * .093, "#e03131"))
            b.add(line(uid("c"), x + w * .79, ry, -w * .11, h * .093, "#e03131"))
    return w, h


def door(b, cx, top, w):
    h = w * SHAPE_RATIO["door"]
    x = cx - w / 2
    b.add(rect(uid("dr"), x, top, w, h, stroke=INK, bg=PALETTE["peach"],
               radius=False))
    b.add(rect(uid("dr"), x + w * .10, top + h * .066, w * .79, h * .867,
               stroke=INK, bg="transparent", radius=False))
    b.add(ellipse(uid("dr"), x + w * .74, top + h / 2, w * .09, w * .09,
                  stroke=INK, bg=INK))
    return w, h


def cloud(b, cx, top, w):
    h = w * SHAPE_RATIO["cloud"]
    b.add(ellipse(uid("cl"), cx - w / 2, top + h * .32, w * .47, h * .64,
                  stroke=INK, bg=PALETTE["sky"]))
    b.add(ellipse(uid("cl"), cx - w * .24, top, w * .50, h * .88,
                  stroke=INK, bg=PALETTE["sky"]))
    b.add(ellipse(uid("cl"), cx + w * .04, top + h * .28, w * .46, h * .66,
                  stroke=INK, bg=PALETTE["sky"]))
    return w, h


def ring(b, cx, top, w):
    b.add(ellipse(uid("r"), cx - w / 2, top, w, w, stroke=INK,
                  bg="transparent", strokeStyle="dashed"))
    for dx, dy in ((-.2, .32), (.1, .28), (-.06, .55), (-.22, .68), (.16, .6)):
        b.add(ellipse(uid("r"), cx + w * dx, top + w * dy, w * .1, w * .1,
                      stroke=INK, bg=INK))
    return w, w


def rng(b, cx, top, w):
    h = w * SHAPE_RATIO["range"]
    b.add(rect(uid("ip"), cx - w / 2, top, w, h, stroke=INK,
               bg=PALETTE["lilac"], strokeStyle="dotted", radius=False))
    return w, h


SHAPES = {"doc": doc, "padlock": padlock, "tag": tag, "clipboard": clipboard,
          "door": door, "cloud": cloud, "ring": ring, "range": rng}


# ------------------------------------------------------------------ lettering

# The panel currently being drawn, as (x, y, w, h). Lettering is clamped to it:
# a long label centred on an edge column would otherwise run out of the frame,
# which is invisible at board zoom and was shipped once already.
BOUNDS = [None]
MARGIN = 46


def clamp(cx, width):
    if not BOUNDS[0]:
        return cx
    x, _, w, _ = BOUNDS[0]
    return min(max(cx, x + MARGIN + width / 2), x + w - MARGIN - width / 2)


def label(b, s, cx, y, size=22, color=INK):
    w, h = measure(s, size)
    cx = clamp(cx, w)
    b.add(txt(uid("t"), cx - w / 2, y, s, size, color))
    return w, h


def marker(b, s, cx, y, tint="peach", size=26):
    """Hand-lettered label on a highlighter swipe."""
    w, h = measure(s, size)
    cx = clamp(cx, w + 28)
    b.add(rect(uid("hl"), cx - w / 2 - 14, y - 5, w + 28, h + 12,
               stroke="transparent", bg=colour(tint), radius=True))
    b.add(txt(uid("t"), cx - w / 2, y, s, size, INK))
    return w + 28, h + 12


def wash(b, cx, cy, w, tint):
    if tint and tint != "none":
        b.add(ellipse(uid("w"), cx - w / 2, cy - w * .38, w, w * .76,
                      stroke="transparent", bg=colour(tint)))


# ---------------------------------------------------------------------- items

def item_size(item, w):
    """Reserve space for an item before drawing it."""
    if "shape" in item:
        return w, w * SHAPE_RATIO[item["shape"]]
    src = LIBS.get(item["icon"][0], item["icon"][0])
    entry = lib.find_item(src, item["icon"][1])
    if not entry:
        raise SystemExit(f"icon not found: {item['icon']}")
    els = entry["elements"]
    if item["icon"][0] in STRIP_TEXT:
        els = [e for e in els if e.get("type") != "text"] or els
    _, _, bw, bh = lib.bbox(els)
    return w, (w * bh / bw if bw else w)


def item_height(item, w, note_width=None, label_size=21):
    """Total drawn height: icon, then label or marker, then note.

    The grid used to reserve a fixed allowance for the note. A six-line note is
    far taller than that, so the next row was drawn straight over it.
    """
    h = item_size(item, w)[1]
    if item.get("marker"):
        h += 16 + measure(item["marker"], 26)[1] + 12
    elif item.get("label"):
        h += 16 + measure(wrap_text(item["label"], label_size,
                                    note_width or w * 2.1), label_size)[1]
    if item.get("full"):
        h += 4 + measure(wrap_text(item["full"], FULL_SIZE,
                                   note_width or w * 2.1), FULL_SIZE)[1]
    if item.get("note"):
        size = item.get("note_size", 17)
        note = wrap_text(item["note"], size,
                         note_width or item.get("note_width", w * 2.1))
        h += 8 + measure(note, size)[1]
    return h


def draw_item(b, item, cx, top, w, label_size=21, note_width=None):
    """Draw wash, then the shape or icon, then its label or marker beneath."""
    iw, ih = item_size(item, w)
    if item.get("wash"):
        wash(b, cx, top + ih * .45, w * 1.32, item["wash"])
    if "shape" in item:
        SHAPES[item["shape"]](b, cx, top, w)
    else:
        src = LIBS.get(item["icon"][0], item["icon"][0])
        entry = lib.find_item(src, item["icon"][1])
        els, _ = lib.stamp(entry, cx - w / 2, top, target_w=w, uid=uid("lib"),
                           drop_text=item["icon"][0] in STRIP_TEXT)
        b.add(*els)

    bottom = top + ih
    if item.get("marker"):
        _, mh = marker(b, item["marker"], cx, bottom + 16, item.get("tint", "peach"))
        bottom += 16 + mh
    elif item.get("label"):
        # Wrap to the column like the note and the expansion. A long service
        # name ("Network Security Group") is wider than a four-column cell and
        # sat on top of its neighbour.
        ltxt = wrap_text(item["label"], label_size, note_width or w * 2.1)
        lw2, lh = measure(ltxt, label_size)
        e = txt(uid("t"), clamp(cx, lw2) - lw2 / 2, bottom + 16, ltxt,
                label_size, INK)
        e["textAlign"] = "center"
        b.add(e)
        bottom += 16 + lh
    if item.get("full"):
        # Wrap it like the note. "Application Programming Interface" on one line
        # is wider than a grid column and ran into the neighbouring item.
        ftxt = wrap_text(item["full"], FULL_SIZE, note_width or w * 2.1)
        fw, fh = measure(ftxt, FULL_SIZE)
        e = txt(uid("t"), clamp(cx, fw) - fw / 2, bottom + 4, ftxt,
                FULL_SIZE, FULL_C)
        e["textAlign"] = "center"
        b.add(e)
        bottom += 4 + fh
    if item.get("note"):
        note = wrap_text(item["note"], item.get("note_size", 17),
                         note_width or item.get("note_width", w * 2.1))
        e_w, nh = measure(note, item.get("note_size", 17))
        e = txt(uid("t"), clamp(cx, e_w) - e_w / 2, bottom + 8, note,
                item.get("note_size", 17), MUTED)
        e["textAlign"] = "center"
        b.add(e)
        bottom += 8 + nh
    return bottom - top


def wrap_text(s, size, width):
    words, lines, cur = s.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if measure(t, size)[0] <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return "\n".join(lines)


# -------------------------------------------------------------------- layouts

def hub(b, x, y, w, h, panel):
    """One item at the centre, the rest ringed around it, arrows pointing in."""
    cx, cy = x + w / 2, y + h / 2
    centre = panel["centre"]
    cw = centre.get("size", 160)
    _, chh = item_size(centre, cw)
    draw_item(b, centre, cx, cy - chh / 2 - 20, cw)

    items = panel["items"]
    sw = panel.get("item_size", 145)
    corners = [(x + 190, y + 110), (x + w - 190, y + 100),
               (x + 190, y + h - 280), (x + w - 190, y + h - 280)]
    for it, (ix, iy) in zip(items, corners):
        draw_item(b, it, ix, iy, sw)
        _, ihh = item_size(it, sw)
        inward = 95 if ix < cx else -95
        b.add(arrow(uid("a"), ix + inward, iy + ihh / 2,
                    (cx + (-130 if ix < cx else 130)) - (ix + inward),
                    cy - 30 - (iy + ihh / 2), color=MUTED))


def row(b, x, y, w, h, panel):
    """A source at the top, items in a row beneath, each with an optional gate."""
    cx = x + w / 2
    src = panel.get("source")
    top = y + 80
    if src:
        sw = src.get("size", 330)
        _, sh = item_size(src, sw)
        SHAPES[src["shape"]](b, cx, top, sw)
        label(b, src["label"], cx + sw * .94, top + sh * .32, 24)
        top += sh

    items = panel["items"]
    iw = panel.get("item_size", 100)
    step = w / (len(items) + 1)
    gate = panel.get("gate")
    gate_y = y + h - 260
    for k, it in enumerate(items):
        ix = x + step * (k + 1)
        label(b, it["label"], ix, top + 46, 20)
        b.add(arrow(uid("a"), cx + (k - (len(items) - 1) / 2) * 70, top + 16,
                    ix - (cx + (k - (len(items) - 1) / 2) * 70), 36, color=MUTED))
        _, ihh = item_size(it, iw)
        draw_item(b, {k2: v for k2, v in it.items() if k2 != "label"},
                  ix, top + 80, iw)
        if gate:
            b.add(arrow(uid("a"), ix, top + 80 + ihh + 4, 0,
                        gate_y - (top + 80 + ihh) - 8, color=MUTED))
            draw_item(b, gate, ix, gate_y, gate.get("size", 60))
    if panel.get("marker"):
        marker(b, panel["marker"], cx, y + h - 110, panel.get("tint", "peach"))


def grid(b, x, y, w, h, panel):
    """Rows by columns, with light connectors so it reads as one family."""
    items = panel["items"]
    cols = panel.get("cols", 3)
    iw = panel.get("item_size", 130)
    nrows = (len(items) + cols - 1) // cols

    # Equal columns spanning the panel. Sizing the inset from the ICON width
    # instead left the outer columns so near the edge that their wide notes were
    # clamped back inward, landing on the neighbouring column.
    col_w = (w - 2 * MARGIN) / cols

    # Rows are measured from real content, notes included. A fixed allowance
    # meant a six-line note had the next row drawn straight over it.
    note_w = col_w * 0.86
    row_h = [max(item_height(it, iw, note_w)
                 for it in items[r * cols:(r + 1) * cols])
             for r in range(nrows)]
    spacing = 54
    total = sum(row_h) + spacing * (nrows - 1)

    # Auto-fit: if the measured rows do not fit the panel, close the gaps first,
    # then shrink the icons. Better than silently overflowing, and better than
    # making the spec author guess a panel height.
    avail = h - 120 - (MARGIN + 40)
    if total > avail and nrows > 1:
        spacing = max(16, spacing - (total - avail) / (nrows - 1))
        total = sum(row_h) + spacing * (nrows - 1)
    if total > avail:
        k = max(0.55, avail / total)
        iw *= k
        note_w = col_w * 0.86
        row_h = [max(item_height(it, iw, note_w)
                     for it in items[r * cols:(r + 1) * cols])
                 for r in range(nrows)]
        total = sum(row_h) + spacing * (nrows - 1)

    top0 = y + max(MARGIN + 40, (h - 120 - total) / 2)

    pos = []
    for i, it in enumerate(items):
        c, r = i % cols, i // cols
        cx = x + MARGIN + col_w * (c + 0.5)
        top = top0 + sum(row_h[:r]) + spacing * r
        draw_item(b, it, cx, top, iw, note_width=note_w)
        pos.append((cx, top, item_size(it, iw)[1]))
    for i in range(len(pos) - 1):
        (ax, ay, ah), (bx, by, _) = pos[i], pos[i + 1],
        if abs(ay - by) < 1:
            b.add(arrow(uid("k"), ax + iw * .9, ay + ah / 2,
                        (bx - iw * .9) - (ax + iw * .9), 0, color="#c9bfae"))


def pair(b, x, y, w, h, panel):
    """Left item, arrow, right item — optionally a barrier stopping the arrow."""
    left, right = panel["left"], panel["right"]
    lw = left.get("size", 240)
    rw = right.get("size", 190)
    lx, rx = x + w * .26, x + w * .74
    _, lh = item_size(left, lw)
    _, rh = item_size(right, rw)
    top = y + (h - max(lh, rh)) / 2 - 40
    draw_item(b, left, lx, top, lw)
    draw_item(b, right, rx, top, rw)
    mid = top + max(lh, rh) / 2
    stop = panel.get("blocked", False)
    end = rx - rw / 2 - (60 if stop else 20)
    b.add(arrow(uid("a"), lx + lw / 2 + 30, mid, end - (lx + lw / 2 + 30), 0,
                color="#862e9c"))
    if stop:
        b.add(line(uid("bar"), end + 16, mid - 32, 0, 64, "#862e9c"))


def stack(b, x, y, w, h, panel):
    """A labelled card of stacked rows — an anatomy diagram."""
    rows = panel["rows"]
    cw, chh = w * .48, h * .42
    rx, ry = x + w * .28, y + 170
    b.add(rect(uid("card"), rx, ry, cw, chh, stroke=INK, bg="#ffffff"))
    for i, r in enumerate(rows):
        by = ry + i * (chh / len(rows))
        b.add(rect(uid("row"), rx + 14, by + 16, cw - 28, chh / len(rows) - 30,
                   stroke="transparent", bg=colour(r.get("wash", "none")),
                   radius=True))
        tw, _ = measure(r["label"], 24)
        b.add(txt(uid("t"), rx - tw - 30, by + chh / (2 * len(rows)) - 14,
                  r["label"], 24, INK))
        if r.get("marker"):
            marker(b, r["marker"], rx + cw / 2, by + 34, r.get("tint", "mint"), 28)
    if panel.get("flow"):
        a, c = panel["flow"]
        b.add(arrow(uid("a"), rx + cw - 60, ry + chh * (a + .5) / len(rows),
                    0, chh * (c - a) / len(rows), color=INK))
    aside = panel.get("aside")
    if aside:
        ax = x + w * .82
        _, ah = item_size(aside, aside.get("size", 96))
        draw_item(b, aside, ax, y + 250, aside.get("size", 96))


def layers(b, x, y, w, h, panel):
    """Stacked horizontal bands — a tiered architecture. Each band carries a
    name on the left and the services that live at that tier on the right."""
    bands = panel["bands"]
    pad = 54
    top0 = y + 96
    band_h = (h - 150) / len(bands)
    icon_w = panel.get("item_size", 46)

    # The icon row starts clear of the widest band caption. A fixed gutter meant
    # the longest note ran straight into the first icon.
    gutter = max(max(measure(bd["label"], 21)[0],
                     measure(bd.get("note", ""), 15)[0] if bd.get("note") else 0)
                 for bd in bands) + 26 + 46

    for i, band in enumerate(bands):
        top = top0 + i * band_h
        b.add(rect(uid("band"), x + pad, top, w - 2 * pad, band_h - 14,
                   stroke="#cfc4b2", bg=colour(band.get("wash", "none")),
                   radius=True))
        lw, lh = measure(band["label"], 21)
        nh = measure(band["note"], 15)[1] if band.get("note") else 0
        block = top + (band_h - 14) / 2 - (lh + nh + 4) / 2
        b.add(txt(uid("t"), x + pad + 26, block, band["label"], 21, INK))
        if band.get("note"):
            b.add(txt(uid("t"), x + pad + 26, block + lh + 4, band["note"], 15,
                      MUTED))

        items = band["items"]
        area_x = x + pad + gutter
        area_w = (w - 2 * pad) - gutter - 40
        step = area_w / len(items)

        # These libraries vary wildly in aspect — Azure's Entra ID icon is a
        # tall pyramid — so cap each icon by HEIGHT, not width, or it grows out
        # through the band. Then sit every label on one baseline so the row
        # does not read as ragged.
        # Size every icon to a common HEIGHT, then clamp its width to the
        # column. Sizing by width alone made GCP's wide card-shaped icons a
        # fraction of the size of Azure's tall ones in the same row.
        target_h = (band_h - 14) * 0.40
        sized = []
        for it in items:
            base_h = item_size(it, icon_w)[1]
            iwi = icon_w * (target_h / base_h) if base_h else icon_w
            iwi = min(iwi, step * 0.72, icon_w * 3.2)
            sized.append((iwi, item_size(it, iwi)[1]))
        tall = max(h2 for _, h2 in sized)
        # Reserve for the tallest icon PLUS the label and any expansion line,
        # then centre that whole block. Anchoring on the icon alone pushed the
        # expansion of the bottom band out through the panel edge.
        lab_h = max(measure(i["label"], 15)[1] for i in items)
        full_h = max((2 + measure(wrap_text(i["full"], FULL_SIZE_BAND,
                                            step * 0.9), FULL_SIZE_BAND)[1])
                     for i in items if i.get("full")) if any(
                         i.get("full") for i in items) else 0
        block = tall + 8 + lab_h + full_h
        label_y = top + (band_h - 14) / 2 - block / 2 + tall + 8

        for k, it in enumerate(items):
            cx = area_x + step * (k + .5)
            icon_w_i, ih = sized[k]
            # Centre the whole icon + label + expansion block, not just the
            # icon — otherwise the extra line hangs below the band edge.
            lh = measure(it["label"], 15)[1]
            fh = 0
            if it.get("full"):
                fh = 2 + measure(wrap_text(it["full"], FULL_SIZE_BAND,
                                           step * 0.9), FULL_SIZE_BAND)[1]
            itop = label_y - 8 - ih
            if it.get("wash"):
                wash(b, cx, itop + ih * .45, icon_w * 1.5, it["wash"])
            src = LIBS.get(it["icon"][0], it["icon"][0])
            entry = lib.find_item(src, it["icon"][1])
            if not entry:
                raise SystemExit(f"icon not found: {it['icon']}")
            els, _ = lib.stamp(entry, cx - icon_w_i / 2, itop,
                               target_w=icon_w_i, uid=uid("lib"),
                               drop_text=it["icon"][0] in STRIP_TEXT)
            b.add(*els)
            label(b, it["label"], cx, label_y, 15)
            if it.get("full"):
                # Wrap to the column: "Elastic Container Service" on one line is
                # wider than the gap between two icons, and ran into its neighbour.
                ftxt = wrap_text(it["full"], FULL_SIZE_BAND, step * 0.9)
                fw, fh = measure(ftxt, FULL_SIZE_BAND)
                e = txt(uid("t"), clamp(cx, fw) - fw / 2,
                        label_y + measure(it["label"], 15)[1] + 2,
                        ftxt, FULL_SIZE_BAND, FULL_C)
                e["textAlign"] = "center"
                b.add(e)

    if panel.get("side"):
        sw, sh = measure(panel["side"], 17)
        b.add(txt(uid("t"), x + w - pad - sw - 10, top0 - 34, panel["side"],
                  17, MUTED))


def flow(b, x, y, w, h, panel):
    """A plain box-and-arrow diagram: nodes on a col/row grid, edges between.

    This is the one thing the retired `excalidraw-diagram` skill could do that
    the structured layouts could not. Nodes are placed and edges routed here, so
    a structural diagram gets the same bounds and collision checking as every
    other panel — hand-computed coordinates never had that.

        "nodes": [{"id": "lb", "label": "Load balancer", "col": 1, "row": 0,
                   "wash": "sky", "note": "health checks"}],
        "edges": [["client", "lb"], ["lb", "app", "http"]]
    """
    nodes = panel["nodes"]
    edges = panel.get("edges", [])
    gap_y = panel.get("gap_y", 70)
    node_h = panel.get("node_h", 78)
    cols = max(n.get("col", 0) for n in nodes) + 1
    rows = max(n.get("row", 0) for n in nodes) + 1

    # Reserve room for the labels the edges carry, but cap what they can claim.
    # A gap narrower than a label pushed it onto the neighbouring node's text;
    # an uncapped one let a 30-character label inflate the gap to 450px and
    # starve the nodes either side down to unreadable boxes.
    EDGE_W = 210
    edge_txt = {id(e): wrap_text(e[2], 16, EDGE_W) for e in edges if len(e) > 2}
    widest_edge = max((measure(t, 16)[0] for t in edge_txt.values()), default=0)
    room = (w - 2 * MARGIN) / (max(cols, 2) + 1)
    gap_x = panel.get("gap_x", max(90, min(widest_edge + 40, room)))

    # Column widths come from the widest label in each column, so a long name
    # widens only its own column instead of stretching the whole diagram.
    col_w = []
    for c in range(cols):
        band = [n for n in nodes if n.get("col", 0) == c]
        widest = max((measure(n["label"], 20)[0] for n in band), default=120)
        col_w.append(max(150, min(widest + 48, (w - 2 * MARGIN) / cols - gap_x)))

    total_w = sum(col_w) + gap_x * (cols - 1)
    extra = max((measure(n.get("note", ""), 16)[1] for n in nodes
                 if n.get("note")), default=0)
    tallest = max((measure(wrap_text(n["label"], 20,
                                     col_w[n.get("col", 0)] - 20), 20)[1] + 34)
                  for n in nodes)
    node_h = max(node_h, tallest)
    total_h = rows * (node_h + extra) + gap_y * (rows - 1)
    x0 = x + (w - total_w) / 2
    y0 = y + (h - 120 - total_h) / 2

    box = {}
    for n in nodes:
        c, r = n.get("col", 0), n.get("row", 0)
        nx = x0 + sum(col_w[:c]) + gap_x * c
        ny = y0 + r * (node_h + extra + gap_y)
        bw, bh = col_w[c], node_h
        # Wrap the label to the box. An unwrapped long name is wider than its
        # own box, spills into the gap, and lands on the edge label there.
        ltxt = wrap_text(n["label"], 20, bw - 20)
        lw, lh = measure(ltxt, 20)
        bh = max(node_h, lh + 34)
        b.add(rect(uid("n"), nx, ny, bw, bh, stroke=INK,
                   bg=colour(n.get("wash", "none")), radius=True))
        e = txt(uid("t"), nx + (bw - lw) / 2, ny + (bh - lh) / 2, ltxt, 20, INK)
        e["textAlign"] = "center"
        b.add(e)
        if n.get("note"):
            nt = wrap_text(n["note"], 16, bw + 40)
            nw, nh = measure(nt, 16)
            e = txt(uid("t"), nx + (bw - nw) / 2, ny + bh + 6, nt, 16, MUTED)
            e["textAlign"] = "center"
            b.add(e)
        box[n["id"]] = (nx, ny, bw, bh)

    for edge in edges:
        src, dst = edge[0], edge[1]
        lab = edge[2] if len(edge) > 2 else None
        if src not in box or dst not in box:
            raise SystemExit(f"flow: edge references unknown node {src}->{dst}")
        ax, ay, aw, ah = box[src]
        bx, by, bw2, bh2 = box[dst]
        # Leave from the side that faces the target, so arrows never cut
        # through the box they start in.
        if abs((bx + bw2 / 2) - (ax + aw / 2)) > abs((by + bh2 / 2) - (ay + ah / 2)):
            if bx > ax:
                sx, sy, ex, ey = ax + aw + 8, ay + ah / 2, bx - 8, by + bh2 / 2
            else:
                sx, sy, ex, ey = ax - 8, ay + ah / 2, bx + bw2 + 8, by + bh2 / 2
        else:
            if by > ay:
                sx, sy, ex, ey = ax + aw / 2, ay + ah + 8, bx + bw2 / 2, by - 8
            else:
                sx, sy, ex, ey = ax + aw / 2, ay - 8, bx + bw2 / 2, by + bh2 + 8
        b.add(arrow(uid("a"), sx, sy, ex - sx, ey - sy, color=INK,
                    curved=False))
        if lab:
            lab = edge_txt.get(id(edge), lab)
            lw, lh = measure(lab, 16)
            dx, dy = ex - sx, ey - sy
            n = (dx * dx + dy * dy) ** 0.5 or 1
            px, py = -dy / n, dx / n
            # Clear the boxes, not just the arrow. A label wider than the gap
            # between two nodes lands on a node's own label otherwise.
            if abs(dy) < 4:                      # horizontal edge
                off = lh / 2 + 8
                px, py = 0, -1
            elif abs(dx) < 4:                    # vertical edge
                off = max(24, lw / 2 + 14)
                px, py = -1, 0
            else:
                off = 20
            b.add(txt(uid("t"),
                      (sx + ex) / 2 + px * off - lw / 2,
                      (sy + ey) / 2 + py * off - lh / 2,
                      lab, 16, MUTED))


LAYOUTS = {"hub": hub, "row": row, "grid": grid, "pair": pair,
           "stack": stack, "layers": layers, "flow": flow}
