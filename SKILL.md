---
name: excalidraw-board
description: Build an editable Excalidraw diagram or multi-panel explainer board from a JSON spec, using free community icon libraries. No image generation, no API keys, no cost. Use for "draw me a diagram", "make me an excalidraw board", "explain X as a board", "a visual explainer of X", or any architecture, flow, sequence or layered diagram. Output is a real .excalidraw file you can open and edit, plus an optional PNG and a shareable link.
---

# Excalidraw board

Describes a diagram; places it for you. Every mark is a native Excalidraw
element — community-library icons and drawn primitives — so a board costs
nothing, stays fully editable after import, and renders identically every run.

You write a spec. You never write coordinates.

## Step 0 — research the topic, then find the icons

Two things before writing any spec.

**Get the facts right.** If the board explains something factual — a service, a
protocol, a process — check current sources first rather than writing from
memory. Boards get shared and screenshotted; a wrong claim outlives the diagram.
Say in the board's README what you checked it against.

**Find out which icons exist before designing the panels.** Missing icons change
the design, so discover first:

```bash
python3 scripts/library.py find server     # which icon can I use for X
python3 scripts/library.py search network  # find a whole library by topic
```

`find` searches icon names across every named library at once. If nothing comes
back, the diagram wants shapes and boxes rather than icons — `flow`, `stack` and
the built-in primitives carry most process, org and business diagrams without a
single vendor icon.

## Build

```bash
python3 scripts/build.py specs/flow-demo.json
```

The board lands in `boards/` relative to wherever you ran the command.

Optional, and each needs Playwright (`pip install playwright && playwright
install chromium`):

```bash
python3 scripts/verify_board.py boards/<file>.excalidraw   # structure check
python3 scripts/export_png.py  boards/<file>.excalidraw    # 2x PNG beside it
python3 scripts/share_link.py  boards/<file>.excalidraw    # clickable URL
```

## A panel

A panel picks a `layout` and lists its content.

| Layout | Shape of the idea |
|---|---|
| `flow` | boxes and arrows — a plain structural diagram |
| `layers` | stacked tiers, each holding the things that live at that tier |
| `hub` | one thing at the centre, others ringed around it, arrows pointing in |
| `row` | a source at the top feeding several items, each with an optional gate |
| `grid` | a family of related items, `cols` per row, lightly connected |
| `pair` | left thing, arrow, right thing; `blocked: true` stops the arrow short |
| `stack` | a card of labelled rows — an anatomy diagram |
| `poster` | one rich block: labelled zones, free placement, connectors |

Several panels in one spec become a story, laid out left to right with arrows
between them. One panel is just a diagram.

## An item

Either a **shape** drawn from primitives, or an **icon** stamped from a library:

```json
{"shape": "doc", "label": "policy file", "wash": "lilac"}
{"icon": ["net", "Server"], "label": "server", "wash": "sky",
 "note": "one per availability zone"}
```

- `label` — the name, 2–5 words
- `marker` — replaces `label`, drawn on a highlighter swipe. Use for the one
  thing in the panel the reader must not miss
- `full` — what an acronym stands for, in rust beneath the label
- `note` — a sentence of detail, muted and wrapped
- `wash` — pastel blob behind the icon: `mint` `lilac` `sky` `peach` `rose` `sage`

Shapes: `doc` `padlock` `tag` `clipboard` `door` `cloud` `ring` `range`.

## Icon libraries

`scripts/library.py` pulls from excalidraw.com's 231 community libraries. Items
are ordinary Excalidraw elements, so they stamp straight in — free, editable and
identical on every run.

```bash
python3 scripts/library.py search aws
python3 scripts/library.py items dwelle/network-topology-icons.excalidrawlib
```

Registered shorthands are in `scene.py` under `LIBS`: `net`, `aws`, `gcp`,
`az` and friends, `people`, `logos`, `office`. Any library works — pass its full
`owner/name.excalidrawlib` instead of a shorthand.

**Choosing a library, in order:**

1. Search the index by domain word, not by service name.
2. List the items. **If they come back as `item-0 … item-N`, reject it** —
   roughly half the catalogue is the older format with unnamed items, and
   identifying those means rendering each one by hand. This is the single
   biggest filter.
3. Grep the named list for what the board actually needs *before* committing to
   a design. Missing icons change the design.
4. Label what the icon actually draws. The network library has no laptop and no
   phone; calling its desktop icon "laptop" is simply wrong and nothing here
   catches it.

**Icons that carry their own text.** Every AWS, Azure and GCP icon bakes a
caption into the artwork, and some are wrong for general use — CloudWatch's
reads "Instance with CloudWatch". `STRIP_TEXT` in `scene.py` lists libraries
whose text is dropped at stamp time so the spec's label is the only one. Check
for this when adding a library.

## Design rules

- **One colour per logical zone.** The reader should see the structure before
  reading a word.
- **Never colour text with its own zone's stroke colour.** Text inside a filled
  shape is `#1e1e1e` or `#343a40`.
- **Labels are 2–5 words.** Anything longer is a `note`.
- **Every non-obvious arrow gets a label.** An unlabelled arrow is a guess the
  reader has to make.

## Two checks that fail the build

Both catch defects that are invisible when you look at a whole board zoomed out,
and both have caught real ones:

- **bounds** — every mark inside its own panel
- **collisions** — no two pieces of lettering overlapping

`problems: 0` is the only passing result. Fix the spec; do not ignore the count.

To judge a board, render panels **individually**. A fit-to-screen screenshot of
a seven-panel board hides everything.

## Traps

- **Never judge lettering from a local Excalidraw canvas server.** It
  mis-renders characters that are fine in the file. Check on excalidraw.com.
- **Old library items lack modern schema fields.** `stamp()` fills them; without
  that the import is silently dropped.
- **Two library formats exist** (v1 `library`, v2 `libraryItems`). `load()`
  handles both.
