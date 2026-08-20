---
name: excalidraw-board
description: Build an editable Excalidraw diagram or multi-panel explainer board from a JSON spec, using free community icon libraries. No image generation, no API keys, no cost. Also imports an existing Mermaid flowchart. Use for "draw me a diagram", "make me an excalidraw board", "explain X as a board", "a visual explainer of X", "turn this Mermaid into Excalidraw", or any architecture, flow, sequence or layered diagram. Output is a real .excalidraw file you can open and edit, plus an optional PNG and a shareable link.
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

**Already have a Mermaid flowchart? Start there instead** — see *From Mermaid*
below.

```bash
python3 scripts/preview_panels.py specs/flow-demo.json     # one file per panel
python3 scripts/selftest.py                                # is the kit healthy
```

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
| `grid` | a family of related items, `cols` per row, lightly connected. Icons in a row share a baseline, so mismatched heights still read as a row |
| `pair` | left thing, arrow, right thing; `blocked: true` stops the arrow short |
| `stack` | a card of labelled rows — an anatomy diagram |
| `poster` | one rich block: labelled zones, free placement, connectors |

Several panels in one spec become a story, laid out left to right with arrows
between them. One panel is just a diagram.

## From Mermaid

If they already have a Mermaid flowchart, do not rewrite it as a spec by hand:

```bash
python3 scripts/mermaid_to_spec.py diagram.mmd --build
python3 scripts/mermaid_to_spec.py ARCHITECTURE.md --out specs/x.json  # from a fence
pbpaste | python3 scripts/mermaid_to_spec.py - --build
```

It reads `flowchart` and `graph` in all four directions and emits a one-panel
`flow` spec: nodes, every edge, every edge label, ranked into layers and
centred so a parent sits over its children. Panel size is computed from the
content, so the bounds check passes without anyone guessing at a width.

**Flowcharts only.** A sequence, class, state, ER, Gantt or pie diagram is
refused by name rather than half-drawn.

**What does not survive, and is reported each time:** node shapes (a decision
rhombus becomes a box), subgraph grouping (the nodes stay, the box around them
goes), dotted and thick links (plain arrows), and the second head on a
bidirectional link. Tell the user what was dropped — do not let them find out
by comparing.

Useful flags: `--out` writes the spec, `--build` writes the board,
`--head` / `--caption` override the title, `--direction` overrides `TD`/`LR`.
The emitted spec is an ordinary spec — edit it, add icons and washes, rebuild.

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
- `icon_tint` — recolours the icon's **lines**, so a diagram is colour-coded by
  role before a word is read. `red` `green` `blue` `orange` `violet` `teal`
  `grey` `black`, or a `#hex`. Icons only; a drawn shape uses `wash`

Shapes: `doc` `padlock` `tag` `clipboard` `door` `cloud` `ring` `range`.

The community icons are all one grey. Reach for `icon_tint` whenever the reader
needs to see *which kind of thing* each box is:

```json
{"icon": ["net", "Server"], "label": "app server", "icon_tint": "blue"}
{"icon": ["net", "Firewall"], "label": "edge",      "icon_tint": "orange"}
```

Use the eight names rather than a wash name — the washes are pastels meant to
sit *behind* an icon, and as lines they are close to invisible. The build says
so if you try.

## Icon libraries

`scripts/library.py` pulls from excalidraw.com's 231 community libraries. Items
are ordinary Excalidraw elements, so they stamp straight in — free, editable and
identical on every run.

```bash
python3 scripts/library.py search aws
python3 scripts/library.py items dwelle/network-topology-icons.excalidrawlib
```

Registered shorthands are in `scene.py` under `LIBS`: `net`, `aws`, `gcp`,
`az` and friends, `logos`, `office`, plus three that carry non-technical
diagrams: `people` and `figures` (stick people — man, woman, girl, guy,
grandma, child, talking, thinking) and `orgchart` (position and team boxes).
Any library works — pass its full `owner/name.excalidrawlib` instead of a
shorthand.

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

## Theme

A board is cream with six pastel washes. A `theme` block at the top of the spec
overrides that — brand colours, or dark. Everything is optional and merges over
the defaults:

```json
"theme": {
  "background": "#12161d",   "panel":  "#1a2029",   "frame": "#39434f",
  "ink":        "#e9edf2",   "muted":  "#9aa6b4",   "title": "#ffb454",
  "zone":       "#4a5665",   "card":   "#232b36",   "hair":  "#4a5665",
  "full":       "#e0a86a",   "accent": "#c495f0",
  "palette": {"mint": "#12453c", "sky": "#123952"},
  "inks":    {"blue": "#66b8ff"}
}
```

- `background` is the canvas, `panel` the frame's fill, `frame` its outline
- `ink` is lettering and strokes, `muted` notes and captions, `title` headings
- `palette` renames washes, `inks` renames `icon_tint` colours. **Both merge** —
  naming one wash leaves the other five alone, because the drawn shapes ask for
  washes by name and would break without them
- A theme may add new names; a spec can then use them like any other

**Every colour the spec names is checked before anything is drawn.** Lettering
that cannot be seen against the panel, the wash it sits on, or the canvas fails
the build; a wash or a line colour too pale to read prints a note with its
contrast ratio. This exists because `lemon` (`#fff3bf`) scored 1.10 against the
panel, was invisible, and shipped anyway.

**What is NOT checked: the colours inside the community icons.** They carry
their own greys, no theme reaches them, and on a dark board they land around
2.0 against the panel while the build still reports `problems: 0`. Give a
themed board `icon_tint` on its icons, or check them by eye. The same is true
of three colours drawn inside the primitives — the ruled lines on `doc`, and
the ticks and crosses on `clipboard`.

Working example: `specs/theme-demo.json`.

## When to ask, and when to just draw

One short question is cheap. Three is an interrogation, and a diagram built on a
wrong guess wastes more time than either. The rule: **ask at most one question,
and only when the answer changes what you draw.** Otherwise draw the obvious
reading and name the assumption in one line underneath.

**Ask when:**

- **It's their own thing.** "My team", "our onboarding", "my setup" — you know
  nothing about it. Ask for the parts. Never invent someone's business and hand
  it back as if it were theirs; they then have to spot every wrong bit.
- **Two readings give completely different diagrams.** "Draw authentication" —
  the concept, OAuth specifically, or their own login flow? "Draw the pipeline" —
  whose, and which tool?
- **Scope is wide open.** "Draw AWS" could be four services or forty. Ask
  whether they want the shape of it or the detail.

**Don't ask when:**

- **It's a public topic.** "How HTTPS works", "how Tailscale works", "the main
  AWS services" — research it and draw it.
- **They already listed the parts.** "Laptop, VPS, Postgres, S3 backups" is
  everything you need. Draw it.
- **The question is cosmetic.** Colours, icon set, panel count — pick well and
  let them change it. The file is editable; that is the whole point.

**When you do ask, make it one line and offer the likely answer:**

> Do you want the whole platform or just the compute side? I'd default to the
> shape of it in one board.

Then draw as soon as they reply. Do not stack a second question.

## What people actually ask for

Requests arrive in plain language. These are the shapes they take, and what to
reach for. Do not make the user learn the spec format — read the request, pick
the layout, write the spec yourself.

| They say | Use |
|---|---|
| "how X works", "how a request reaches Y" | `flow`, one panel |
| "all of it in one diagram / one block" | `poster` with zones |
| "who does what", "our team", "who owns what" | `grid` with `figures` or `orgchart` |
| "compare A and B", "when to move from A to B" | `flow` left to right, or `pair` |
| "the layers of X", "what sits where" | `layers` |
| "explain X" with several parts | several panels, read left to right |
| "turn this Mermaid into Excalidraw", or they paste Mermaid | `mermaid_to_spec.py` |
| "use our brand colours", "make it dark" | a `theme` block |

When someone names a look — "stick people", "doodle", "with AWS icons" — that is
a library choice, not a layout choice. Run `library.py find` on the noun they
used before deciding the design.

## Design rules

- **One colour per logical zone.** The reader should see the structure before
  reading a word.
- **Never colour text with its own zone's stroke colour.** Text inside a filled
  shape is `#1e1e1e` or `#343a40`.
- **Labels are 2–5 words.** Anything longer is a `note`.
- **Every non-obvious arrow gets a label.** An unlabelled arrow is a guess the
  reader has to make.

## Three checks, and what each one does on failure

Each catches a defect that is invisible when you look at a whole board zoomed
out, and each has caught a real one:

- **contrast** — lettering you cannot see against the panel or the canvas it
  sits on. Runs before anything is drawn, so it **stops the write**: no file
  appears. A wash or line colour merely too pale earns a note instead
- **bounds** — every mark inside its own panel
- **collisions** — no two pieces of lettering overlapping

Bounds and collisions run while the board is drawn, so **the file is written
either way** — deliberately, because a broken board is easier to fix once you
have opened it. They set the problem count and the exit code.

`problems: 0` is the only passing result. Fix the spec; do not ignore the count,
and do not take the file existing as a sign that it is fine.

To judge a board, look at panels **individually**. A fit-to-screen screenshot of
a seven-panel board is about 14% zoom, and overlaps, clipped labels and
mis-centred captions all disappear at that scale:

```bash
python3 scripts/preview_panels.py <spec.json>          # one file per panel
python3 scripts/preview_panels.py <spec.json> --panel 3   # just that one
python3 scripts/preview_panels.py <spec.json> --png     # render them too
```

Each panel is rebuilt through the ordinary build path, so what you open is
exactly what the board contains — and the problem count is reported per panel,
which names the panel at fault instead of the board.

## Traps

- **Never judge lettering from a local Excalidraw canvas server.** It
  mis-renders characters that are fine in the file. Check on excalidraw.com.
- **Old library items lack modern schema fields.** `stamp()` fills them; without
  that the import is silently dropped.
- **Two library formats exist** (v1 `library`, v2 `libraryItems`). `load()`
  handles both.
- **If something behaves oddly, run `python3 scripts/selftest.py` first.** It
  builds every shipped spec and then deliberately breaks things to confirm each
  check still fails — so a green run means the kit is fine and the spec is not.
