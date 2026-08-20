#!/usr/bin/env python3
"""Turn a Mermaid flowchart into a board spec — paste Mermaid, get an editable board.

    python3 scripts/mermaid_to_spec.py diagram.mmd --build
    python3 scripts/mermaid_to_spec.py README.md --out specs/arch.json
    pbpaste | python3 scripts/mermaid_to_spec.py -

Writing a spec by hand is a real first step to ask of someone who already has
diagrams in their repo. Most of those diagrams are Mermaid, and Mermaid renders
to a flat picture. This reads one and emits a spec for the `flow` layout, so the
same diagram comes back as a file you can drag around.

**Flowcharts only.** `flowchart` and `graph` in any of the four directions.
Every other Mermaid diagram type is refused by name rather than half-parsed —
a sequence diagram silently rendered as boxes would be worse than no output.

What survives the trip: nodes, their text, every edge, and every edge label.
What does not: node shapes (a decision rhombus becomes a box), subgraph
grouping (the nodes stay, the box around them goes), link styles (dotted, thick
and invisible links all become plain arrows), and the second head on a
two-headed link. Anything dropped is reported, not passed over.

Input can be a `.mmd` file, a Markdown file with a ```mermaid fence, or stdin.
"""

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from excalidraw_kit import measure                            # noqa: E402

# One colour per rank, so the reader sees the shape of the graph before reading
# a word. Cycles if the graph is deeper than the palette.
RANK_WASH = ["sky", "mint", "lilac", "peach", "rose", "sage"]

# Diagram types this deliberately refuses, so the message names the real reason.
OTHER_TYPES = {
    "sequencediagram": "sequence diagram", "classdiagram": "class diagram",
    "statediagram": "state diagram", "statediagram-v2": "state diagram",
    "erdiagram": "entity relationship diagram", "journey": "user journey",
    "gantt": "Gantt chart", "pie": "pie chart", "mindmap": "mindmap",
    "timeline": "timeline", "gitgraph": "git graph", "sankey-beta": "Sankey",
    "quadrantchart": "quadrant chart", "requirementdiagram": "requirements",
    "c4context": "C4 context", "block-beta": "block diagram",
    "xychart-beta": "xy chart", "flowchart-elk": "flowchart-elk",
}

# Node-shape openers, longest first, each with the length of its closing token.
# Only the outer bracket depth is counted, which is why one entry per opener is
# enough: "[/x/]" and "[/x\\]" both open with "[" and close two characters wide.
OPENERS = [("(((", 3), ("[[", 2), ("[(", 2), ("([", 2), ("[/", 2), ("[\\", 2),
           ("((", 2), ("{{", 2), ("[", 1), ("(", 1), ("{", 1), (">", 1)]
CLOSER = {"[": "]", "(": ")", "{": "}", ">": "]"}

# An id may contain a hyphen between two alphanumeric runs ("api-gw") but can
# never end on one, which is what keeps "A-->B" from being read as one id.
ID = r"[A-Za-z0-9_.]+(?:-[A-Za-z0-9_.]+)*"
ID_RE = re.compile(ID)

# Arrow-head last, so "--" cannot win before the arrow form has been tried. The
# leading group takes o and x as well as <, because "A o--o B" otherwise reads
# its own left-hand arrowhead as an identifier and invents a node called "o".
LINK_RE = re.compile(r"[<ox]?(?:-\.+-|={2,}|-{2,}|~{2,})[>ox]?")
LABEL_RE = re.compile(r"\|([^|]*)\|")

SKIP_RE = re.compile(r"^(classDef|class|style|linkStyle|click|direction"
                     r"|accTitle|accDescr)\b")
SUBGRAPH_RE = re.compile(r"^subgraph\s+(.*)$", re.I)

# "A -- text --> B" written the long way. Rewritten to the pipe form so the
# scanner has one shape to handle instead of three.
MIDDLE = [
    (re.compile(r"-{2,}\s+([^|>\n]+?)\s+(-{2,}[>ox]|-{2,})"), r"\2|\1|"),
    (re.compile(r"={2,}\s+([^|>\n]+?)\s+(={2,}[>ox]|={2,})"), r"\2|\1|"),
    (re.compile(r"-\.+\s+([^|>\n]+?)\s+\.-([>ox]?)"), r"-.-\2|\1|"),
]


class MermaidError(Exception):
    pass


# ------------------------------------------------------------------- reading

def extract(text):
    """Pull the Mermaid out of a Markdown fence, or take the text as-is."""
    fences = re.findall(r"```+\s*mermaid\s*\n(.*?)```+", text,
                        re.S | re.I)
    if len(fences) > 1:
        print(f"  note: {len(fences)} mermaid blocks found, importing the "
              f"first. Split the file to import the others.", file=sys.stderr)
    return fences[0] if fences else text


def take_frontmatter(text):
    """Mermaid's `--- title: X ---` header. Returns (title, remaining text)."""
    m = re.match(r"\s*---\s*\n(.*?)\n\s*---\s*\n", text, re.S)
    if not m:
        return None, text
    title = re.search(r"^\s*title\s*:\s*(.+?)\s*$", m.group(1), re.M)
    return (title.group(1).strip().strip("\"'") if title else None), \
        text[m.end():]


def protect(text):
    """Swap "quoted labels" for placeholders before anything else is stripped.

    Without this a `%%` or a `]` inside a label takes the rest of the line with
    it, and the failure looks like a parser bug rather than a quoting one.
    """
    kept = []

    def hide(m):
        kept.append(m.group(1))
        return f"\x01{len(kept) - 1}\x01"
    return re.sub(r'"([^"\n]*)"', hide, text), kept


def restore(s, kept):
    return re.sub(r"\x01(\d+)\x01", lambda m: kept[int(m.group(1))], s)


def clean_label(s, kept):
    s = restore(s, kept)
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    # "fa:fa-car Car" renders as an icon plus a word in Mermaid. There is no
    # icon here, so the token would print literally.
    s = re.sub(r"\bfa[brsdl]?:fa-[\w-]+\s*", "", s)
    for entity, ch in (("&quot;", '"'), ("&amp;", "&"), ("&lt;", "<"),
                       ("&gt;", ">"), ("&nbsp;", " "), ("#quot;", '"')):
        s = s.replace(entity, ch)
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------------ scanning

def read_group(s, i):
    """Read a node's bracketed text starting at s[i]. Returns (text, end) or None.

    Depth is counted on the outer bracket so `A(foo (bar))` keeps its inner
    parentheses instead of ending at the first closing one.
    """
    for opener, close_len in OPENERS:
        if not s.startswith(opener, i):
            continue
        oc = opener[0]
        cc = CLOSER[oc]
        depth = 0
        j = i
        while j < len(s):
            if s[j] == oc:
                depth += 1
            elif s[j] == cc:
                depth -= 1
                if depth == 0:
                    return s[i + len(opener):j + 1 - close_len], j + 1
            j += 1
        raise MermaidError(f"unclosed {opener!r} in: {s.strip()[:60]}")
    return None


def scan(statement):
    """Statement -> tokens: ('node', id, text|None), ('link', label|None), ('&',)."""
    out, i, n = [], 0, len(statement)
    while i < n:
        ch = statement[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "&":
            out.append(("&",))
            i += 1
            continue
        link = LINK_RE.match(statement, i)
        # A bare ">" opens an asymmetric node, so only treat it as a link when
        # the match is longer than one character.
        if link and len(link.group(0)) > 1:
            i = link.end()
            # Skip a space: `A --> |label| B` is valid Mermaid, and matching at
            # exactly i refused it with a message that read as a parser bug.
            j = i
            while j < n and statement[j] == " ":
                j += 1
            lab = LABEL_RE.match(statement, j)
            if lab:
                i = lab.end()
            out.append(("link", lab.group(1) if lab else None,
                        link.group(0)))
            continue
        ident = ID_RE.match(statement, i)
        if not ident:
            raise MermaidError(f"cannot read {statement[i:i + 24]!r} "
                               f"in: {statement.strip()[:60]}")
        i = ident.end()
        # ":::className" attaches a CSS class; the styling is not carried over.
        cls = re.match(r":::" + ID, statement[i:])
        if cls:
            i += cls.end()
        j = i
        while j < n and statement[j] == " ":
            j += 1
        group = read_group(statement, j) if j < n else None
        if group:
            text, i = group
        else:
            text = None
        out.append(("node", ident.group(0), text))
    return out


# -------------------------------------------------------------------- parsing

class Graph:
    def __init__(self):
        self.labels = {}        # id -> text, in first-seen order
        self.edges = []         # (src, dst, label|None)
        self.subgraphs = {}     # id -> title, materialised only if referenced
        self.dropped = []       # what did not survive, reported to the user

    def node(self, nid, text=None):
        if nid not in self.labels:
            self.labels[nid] = text or self.subgraphs.get(nid) or nid
        elif text:
            self.labels[nid] = text


def parse(source):
    """Mermaid text -> (Graph, direction). Raises MermaidError with a reason."""
    title, source = take_frontmatter(source)
    source, kept = protect(source)
    source = re.sub(r"%%\{.*?\}%%", "", source, flags=re.S)   # init directives
    source = re.sub(r"%%.*", "", source)                      # comments

    lines = [ln.strip() for ln in source.splitlines()]
    lines = [ln for ln in lines if ln]
    if not lines:
        raise MermaidError("no Mermaid found — the input is empty once "
                           "comments are removed")

    head = lines[0]
    m = re.match(r"^(flowchart|graph)\b\s*(TB|TD|BT|RL|LR)?\b", head, re.I)
    if not m:
        word = re.split(r"[\s;:]", head)[0].lower()
        kind = OTHER_TYPES.get(word)
        raise MermaidError(
            f"this is a {kind}, and only flowcharts are supported"
            if kind else
            f"the first line is {head[:40]!r}; expected 'flowchart' or 'graph'")
    direction = (m.group(2) or "TB").upper()
    body = lines[1:]
    if head[m.end():].strip():
        body.insert(0, head[m.end():].strip())

    g = Graph()
    g.title = title
    for raw in body:
        for statement in re.split(r";", raw):
            statement = statement.strip()
            if not statement:
                continue
            if statement.lower() == "end":
                continue
            sub = SUBGRAPH_RE.match(statement)
            if sub:
                rest = sub.group(1).strip()
                sid = ID_RE.match(rest)
                sid = sid.group(0) if sid else rest
                # Skip the space first. `subgraph ide1 [One]` is the form in
                # Mermaid's own documentation, and read_group wants the bracket
                # at exactly the index it is handed — so the title was never
                # extracted and the whole line became the title instead.
                after = len(sid)
                while after < len(rest) and rest[after] == " ":
                    after += 1
                group = read_group(rest, after) if sid != rest else None
                g.subgraphs[sid] = clean_label(group[0] if group else rest, kept)
                g.dropped.append(f"subgraph {g.subgraphs[sid]!r} — the nodes "
                                 f"are kept, the box around them is not")
                continue
            if SKIP_RE.match(statement):
                continue
            for pattern, repl in MIDDLE:
                statement = pattern.sub(repl, statement)
            _statement(g, statement, kept)

    if not g.labels:
        raise MermaidError("the flowchart declares no nodes")
    return g, direction


def _statement(g, statement, kept):
    """One `A[x] --> B & C` line: nodes, links, and the & fan-out between them."""
    tokens = scan(statement)
    group, pending = [], None          # current node group, and the link into it
    for tok in tokens:
        if tok[0] == "node":
            nid, text = tok[1], tok[2]
            g.node(nid, clean_label(text, kept) if text is not None else None)
            group.append(nid)
        elif tok[0] == "&":
            continue
        else:                          # a link closes the group on its left
            if not group:
                raise MermaidError(f"a link with nothing before it: "
                                   f"{statement.strip()[:60]}")
            if pending is not None:
                _join(g, pending[0], group, pending[1], pending[2], kept)
            pending = (group, tok[1], tok[2])
            group = []
    if pending is not None:
        if not group:
            raise MermaidError(f"a link with nothing after it: "
                               f"{statement.strip()[:60]}")
        _join(g, pending[0], group, pending[1], pending[2], kept)


def _join(g, sources, targets, label, kind, kept):
    if kind and kind[0] in "<ox":
        g.dropped.append(f"the head on the left of a two-headed link "
                         f"({kind}) — drawn one way only")
    if kind and "~" in kind:
        # Not a thick link. Mermaid's ~~~ is INVISIBLE, so drawing it as an
        # ordinary arrow is the opposite of what was asked for, and saying
        # "thick" would state a cause the code has not established.
        g.dropped.append(f"an invisible link ({kind}) — drawn as a plain "
                         f"arrow, which is the opposite of what it asks for")
    elif kind and ("." in kind or "=" in kind):
        g.dropped.append(f"a {'dotted' if '.' in kind else 'thick'} link "
                         f"({kind}) — drawn as a plain arrow")
    for a in sources:
        for b in targets:
            if a == b:
                g.dropped.append(f"the self-link on {a!r} — a flow arrow needs "
                                 f"two different boxes")
                continue
            g.edges.append((a, b, clean_label(label, kept)
                            if label else None))


# ------------------------------------------------------------------ placing

def back_edges(g):
    """Edges that close a cycle, found by depth-first search.

    They have to come out before ranking. A three-node cycle ranked naively
    walks its own loop once per pass and lands on ranks 7, 8 and 9 — ten columns
    for three boxes. The edges are still drawn; they just do not get a say in
    where the boxes go.
    """
    out = set()
    colour = {}                                  # node -> 0 on stack, 1 done
    adjacency = {}
    for i, (a, b, _lab) in enumerate(g.edges):
        adjacency.setdefault(a, []).append((b, i))

    for root in g.labels:
        if colour.get(root) is not None:
            continue
        # Iterative, because a long chain would otherwise hit the recursion cap.
        stack = [(root, iter(adjacency.get(root, [])))]
        colour[root] = 0
        while stack:
            node, kids = stack[-1]
            for child, index in kids:
                if colour.get(child) == 0:       # still on the stack: a cycle
                    out.add(index)
                elif colour.get(child) is None:
                    colour[child] = 0
                    stack.append((child, iter(adjacency.get(child, []))))
                    break
            else:
                colour[node] = 1
                stack.pop()
    return out


def rank(g):
    """Longest-path rank per node, over the edges that are not cycle-closing."""
    ranks = {n: 0 for n in g.labels}
    skip = back_edges(g)
    forward = [(a, b) for i, (a, b, _lab) in enumerate(g.edges)
               if i not in skip and a != b]
    for _ in range(len(ranks)):
        moved = False
        for a, b in forward:
            if ranks[b] < ranks[a] + 1:
                ranks[b] = ranks[a] + 1
                moved = True
        if not moved:
            break
    return ranks


def order_lanes(g, ranks):
    """Rank -> the ids in it, ordered to keep connected nodes near each other.

    One barycentre pass: a node moves to the average position of the nodes
    pointing at it. Sorting is stable, so anything with no predecessor keeps the
    order it was written in — the file's own order is the best guess available.
    """
    lanes = {}
    for nid in g.labels:
        lanes.setdefault(ranks[nid], []).append(nid)

    preds = {}
    for a, b, _lab in g.edges:
        if ranks[a] < ranks[b]:
            preds.setdefault(b, []).append(a)

    pos = {n: i for ids in lanes.values() for i, n in enumerate(ids)}
    for r in sorted(lanes)[1:]:
        lanes[r].sort(key=lambda n: (sum(pos[p] for p in preds.get(n, []))
                                     / len(preds[n]) if preds.get(n)
                                     else pos[n]))
        pos.update({n: i for i, n in enumerate(lanes[r])})
    return lanes


def place(g, direction):
    """Assign col/row from the rank, along whichever axis the direction runs."""
    ranks = rank(g)
    depth = max(ranks.values()) + 1
    lanes = order_lanes(g, ranks)

    # Each rank is centred against the widest one, so a parent sits over its
    # children instead of every rank hugging the same edge. Columns stay whole
    # numbers and stay distinct within a rank — two nodes sharing one would be
    # drawn on top of each other.
    widest = max(len(ids) for ids in lanes.values())
    across = {}
    for r, ids in lanes.items():
        offset = (widest - len(ids)) // 2
        for i, nid in enumerate(ids):
            across[nid] = offset + i

    nodes = []
    for nid, text in g.labels.items():
        r = ranks[nid]
        along = depth - 1 - r if direction in ("BT", "RL") else r
        col, row = (across[nid], along) if direction in ("TB", "TD", "BT") \
            else (along, across[nid])
        nodes.append({"id": nid, "label": text, "col": col, "row": row,
                      "wash": RANK_WASH[r % len(RANK_WASH)]})
    return nodes


def panel_height(nodes):
    """Panel height for this many rows.

    Height only. The WIDTH used to be calculated here too, from label metrics
    plus a fudge term, and it came out 1.9x wider than the width that actually
    works — the same mistake build.py already records: a number that is wrong is
    worse than no number. The spec now names no width and build.py measures one.
    """
    rows = max(n["row"] for n in nodes) + 1
    node_h = max(78, measure("x", 20)[1] + 34)
    gap_y = 70
    # 212 is the layout's own floor (it centres content in h - 120 and the
    # bounds check wants 46 clear at the top); the rest is breathing room.
    return max(780, int(rows * node_h + gap_y * (rows - 1) + 232)), gap_y


# -------------------------------------------------------------------- output

DIRECTIONS = ("TB", "TD", "BT", "LR", "RL")


def to_spec(source, head=None, caption=None, out=None, direction=None):
    g, auto_direction = parse(source)
    direction = (direction or auto_direction).upper()
    if direction not in DIRECTIONS:
        raise MermaidError(f"unknown direction {direction!r}. "
                           f"One of {', '.join(DIRECTIONS)}")
    nodes = place(g, direction)
    edges = [[a, b] + ([lab] if lab else []) for a, b, lab in g.edges]
    ph, gap_y = panel_height(nodes)

    # No "panel_w": build.py finds the narrowest width that draws clean, by
    # building it. Naming one here means predicting the layout's own arithmetic,
    # and a second implementation of it drifts from the first.
    spec = {
        "title": head or g.title or "Imported flowchart",
        "out": out or "boards/mermaid.excalidraw",
        "panel_h": ph,
        "panels": [{
            "head": head or g.title or "Imported flowchart",
            "layout": "flow",
            "caption": caption or "",
            "gap_y": gap_y,
            "nodes": nodes,
            "edges": edges,
        }],
    }
    return spec, g


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        sys.exit(__doc__)
    src, opts, i = args[0], {}, 1
    while i < len(args):
        a = args[i]
        if a == "--build":
            opts["build"] = True
            i += 1
        elif a in ("--out", "--board", "--head", "--caption",
                   "--direction") and i + 1 < len(args):
            opts[a[2:]] = args[i + 1]
            i += 2
        else:
            sys.exit(f"unknown or incomplete argument {a!r}\n\n{__doc__}")

    if src == "-":
        text, stem = sys.stdin.read(), "mermaid"
    else:
        p = pathlib.Path(src)
        if not p.exists():
            sys.exit(f"no such file: {src}")
        text, stem = p.read_text(), p.stem
        if p.suffix.lower() in (".md", ".markdown") and "```" in text \
                and extract(text) is text:
            sys.exit(f"{p.name} has fenced blocks but none of them is a "
                     f"```mermaid fence — there is nothing here to import.")

    board = opts.get("board") or f"boards/{stem}.excalidraw"
    try:
        spec, g = to_spec(extract(text), head=opts.get("head"),
                          caption=opts.get("caption"), out=board,
                          direction=opts.get("direction"))
    except MermaidError as exc:
        sys.exit(f"cannot import this diagram: {exc}")

    panel = spec["panels"][0]
    print(f"{len(panel['nodes'])} node(s), {len(panel['edges'])} edge(s), "
          f"{max(n['col'] for n in panel['nodes']) + 1} column(s) x "
          f"{max(n['row'] for n in panel['nodes']) + 1} row(s)",
          file=sys.stderr)
    for line in dict.fromkeys(g.dropped):       # each reason once, in order
        print(f"  dropped: {line}", file=sys.stderr)

    if opts.get("out"):
        dest = pathlib.Path(opts["out"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(spec, indent=2) + "\n")
        print(f"  spec: {dest}", file=sys.stderr)
    elif not opts.get("build"):
        print(json.dumps(spec, indent=2))

    if opts.get("build"):
        import build as B
        errs = B.validate(spec)
        if errs:
            print(f"the imported spec has {len(errs)} problem(s):",
                  file=sys.stderr)
            for e in errs:
                print(f"  - {e}", file=sys.stderr)
            return 1
        b, problems = B.build(spec)
        b.save(pathlib.Path(board))
        print(f"  problems: {problems}")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
