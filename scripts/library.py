#!/usr/bin/env python3
"""Use excalidraw.com's community libraries instead of paying for generated art.

    python3 library.py find server           # which icon can I use for X
    python3 library.py search network        # find libraries by keyword
    python3 library.py items <source>        # list the items inside one
    python3 library.py fetch <source>        # cache it locally

A library item is a group of ordinary Excalidraw elements — the same shapes the
editor draws. Stamping one into a board costs nothing, stays fully editable, and
renders identically every time. A generated image costs ~12 kie.ai credits, is
flat pixels, and comes back slightly different on every run.

Two file formats are in the wild and both appear in the official index:

    v2:  {"type":"excalidrawlib","version":2,"libraryItems":[{"name":…,"elements":[…]}]}
    v1:  {"type":"excalidrawlib","version":1,"library":[[…elements…],[…]]}

`load()` flattens both to a list of {name, elements}.
"""

import json
import hashlib
import pathlib
import sys
import urllib.request

CACHE = pathlib.Path(__file__).resolve().parent.parent / ".cache"
INDEX_URL = ("https://raw.githubusercontent.com/excalidraw/"
             "excalidraw-libraries/main/libraries.json")
RAW = ("https://raw.githubusercontent.com/excalidraw/"
       "excalidraw-libraries/main/libraries/{source}")


def _get(url, dest):
    CACHE.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    with urllib.request.urlopen(url, timeout=60) as r:
        dest.write_bytes(r.read())
    return dest


def index(refresh=False):
    """The official catalogue of every published library."""
    p = CACHE / "libraries.json"
    if refresh and p.exists():
        p.unlink()
    _get(INDEX_URL, p)
    return json.loads(p.read_text())


def search(query):
    q = query.lower()
    return [l for l in index()
            if q in l["name"].lower() or q in l.get("description", "").lower()]


def fetch(source):
    """source is the index's `source` field, e.g. 'lipis/stars.excalidrawlib'."""
    dest = CACHE / source.replace("/", "__")
    return _get(RAW.format(source=source), dest)


_LOADED = {}


def load(source_or_path):
    """Return [{name, elements}], normalising both library formats.

    Memoised on the path. Every icon lookup used to re-read and re-parse the
    whole file, and the auto-fit multiplies that by the number of probe widths:
    a twelve-icon board with no panel_w parsed a 249-item library three hundred
    times. Nothing mutates what comes back — `stamp()` deep-copies before it
    touches anything — so one parse per file is enough.
    """
    if str(source_or_path) in _LOADED:
        return _LOADED[str(source_or_path)]
    p = pathlib.Path(source_or_path)
    if not p.exists():
        p = fetch(str(source_or_path))
    d = json.loads(p.read_text())
    out = []
    if "libraryItems" in d:
        for i, it in enumerate(d["libraryItems"]):
            out.append({"name": it.get("name") or f"item-{i}",
                        "elements": it["elements"]})
    elif "library" in d:
        for i, els in enumerate(d["library"]):
            out.append({"name": f"item-{i}", "elements": els})
    else:
        raise ValueError(f"{p.name}: not an excalidrawlib file")
    _LOADED[str(source_or_path)] = out
    return out


def find_item(source, name_substring):
    """First item whose name contains the substring, case-insensitive."""
    q = name_substring.lower()
    for it in load(source):
        if q in it["name"].lower():
            return it
    return None


# Libraries worth sweeping by default: every one of these has *named* items, so
# a search can actually tell you what it found.
SEARCHABLE = [
    "childishgirl/aws-architecture-icons.excalidrawlib",
    "mguidoti/original-google-architecture-icons.excalidrawlib",
    "youritjang/azure-cloud-services.excalidrawlib",
    "rockssk/microsoft-azure-cloud-icons.excalidrawlib",
    "7demonsrising/azure-compute.excalidrawlib",
    "7demonsrising/azure-network.excalidrawlib",
    "7demonsrising/azure-storage.excalidrawlib",
    "7demonsrising/azure-general.excalidrawlib",
    "7demonsrising/azure-containers.excalidrawlib",
    "ubigene/misc-azure-icons.excalidrawlib",
    "dwelle/network-topology-icons.excalidrawlib",
    "samu_x86/network-elements.excalidrawlib",
    "pclainchard/it-logos.excalidrawlib",
    "esteevens/logos.excalidrawlib",
    "dhtoran/stick-people.excalidrawlib",
    "youritjang/stick-figures.excalidrawlib",
    "m47812/office-items.excalidrawlib",
    "jgodoy/organization-chart.excalidrawlib",
    "rochacbruno/computer-parts.excalidrawlib",
]


def find_icon(term, sources=None, limit=40):
    """Search ITEM names across libraries — 'what icon can I use for X'.

    `search()` matches library titles; this matches the icons inside them,
    which is the question you actually have when writing a spec.
    """
    q = term.lower()
    hits = []
    for src in (sources or SEARCHABLE):
        try:
            for it in load(src):
                if q in it["name"].lower():
                    hits.append((src, it["name"], len(it["elements"])))
                    if len(hits) >= limit:
                        return hits
        except Exception:
            continue
    return hits


def bbox(elements):
    xs = [e["x"] for e in elements]
    ys = [e["y"] for e in elements]
    x2 = [e["x"] + e.get("width", 0) for e in elements]
    y2 = [e["y"] + e.get("height", 0) for e in elements]
    return min(xs), min(ys), max(x2) - min(xs), max(y2) - min(ys)


def stamp(item, x, y, target_w=None, uid="s", tint=None, drop_text=False):
    """Return a copy of the item's elements placed at (x, y).

    Ids are rewritten so the same item can be stamped many times in one board
    without Excalidraw treating the copies as the same element. All copies of one
    stamp share a groupId, so a click selects the whole icon.
    """
    els = json.loads(json.dumps(item["elements"]))   # deep copy
    if drop_text:
        # Several libraries bake a caption into the icon (every AWS icon does,
        # and CloudWatch's reads "Instance with CloudWatch"). Dropping it lets
        # the caller's own label be the only one, and be correct.
        els = [e for e in els if e.get("type") != "text"]
        if not els:
            raise ValueError("item is nothing but text")
    bx, by, bw, bh = bbox(els)
    k = (target_w / bw) if (target_w and bw) else 1.0
    gid = f"lib-{uid}"

    for n, e in enumerate(els):
        e["id"] = f"{uid}-{n}"
        e["seed"] = int(hashlib.sha1(e["id"].encode()).hexdigest()[:8], 16)
        e["versionNonce"] = e["seed"]
        e["x"] = x + (e["x"] - bx) * k
        e["y"] = y + (e["y"] - by) * k
        for dim in ("width", "height", "fontSize"):
            if dim in e and isinstance(e[dim], (int, float)):
                e[dim] = e[dim] * k
        if "points" in e and e["points"]:
            e["points"] = [[p[0] * k, p[1] * k] for p in e["points"]]
        # Library elements predate several schema fields; fill the ones the
        # current editor expects so the import is not silently dropped.
        e.setdefault("roundness", None)
        e.setdefault("frameId", None)
        e.setdefault("boundElements", e.pop("boundElementIds", None) or [])
        e.setdefault("updated", 1)
        e.setdefault("link", None)
        e.setdefault("locked", False)
        e.setdefault("isDeleted", False)
        e["groupIds"] = [gid]
        # Recolour the icon's LINES only, and only the lines that were already
        # visible. Several icons carry an invisible bounding rectangle (the
        # network set's Server has one, stroke "#0000"); tinting that would draw
        # a box around an icon that never had one.
        if tint and not _invisible(e.get("strokeColor")):
            e["strokeColor"] = tint
    return els, (bw * k, bh * k)


def _invisible(colour):
    """True for 'transparent' and for #rgba / #rrggbbaa with a zero alpha."""
    if not colour or colour == "transparent":
        return True
    c = str(colour).lstrip("#")
    if len(c) == 4:
        return c[3] == "0"
    if len(c) == 8:
        return c[6:] == "00"
    return False


def _cli():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "search":
        for l in search(sys.argv[2]):
            print(f"{l['name']:42} {l['source']}")
    elif cmd == "find":
        hits = find_icon(sys.argv[2])
        if not hits:
            print(f"no icon named like {sys.argv[2]!r}. Try a broader word, or "
                  f"'search' to look for a whole library.")
        for src, name, n in hits:
            short = next((k for k, v in
                          {"aws": "childishgirl/aws-architecture-icons.excalidrawlib"}.items()
                          if v == src), None)
            print(f"{name:34} {src.split('/')[1].replace('.excalidrawlib',''):32} "
                  f"{n:3} els")
    elif cmd == "items":
        for it in load(sys.argv[2]):
            print(f"{len(it['elements']):4} els  {it['name']}")
    elif cmd == "fetch":
        print(fetch(sys.argv[2]))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    _cli()
