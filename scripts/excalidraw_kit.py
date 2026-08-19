"""Excalidraw kit — programmatic .excalidraw files with AI images embedded inside.

Two halves:

  1. Element factories (rect / text / arrow / line / ellipse) — the structure.
  2. Board.embed_image() — writes a PNG into the file's `files` map and returns
     an `image` element that points at it.

The second half is the part that makes the output an *editable file containing
AI art* rather than a flat picture. Everything stays selectable, movable and
re-colourable after import.

File format notes, learned from Excalidraw's own exporter:

  files["<id>"] = {mimeType, id, dataURL, created, lastRetrieved}
  dataURL       = "data:image/png;base64,<...>"
  image element = {type:"image", fileId:"<id>", status:"saved", scale:[1,1], ...}

`fileId` is a hex digest of the image bytes. Using a content hash means the same
picture embedded twice costs one copy in the file.

Everything here is deterministic — same inputs produce a byte-identical file, so
diffs are readable and re-runs are free.
"""

import base64
import hashlib
import io
import json
import pathlib

# ---------------------------------------------------------------- text metrics

# Virgil is wide. Measure generously — Excalidraw clips to the stored width on
# import instead of re-measuring, so under-estimating loses characters at BOTH
# ends of centred text. Over-estimating costs nothing.
CH = {1: 0.60, 2: 0.55, 3: 0.62}   # width per char, per font, as a fraction of size
PAD = 1.45                          # safety multiplier

VIRGIL, HELVETICA, CODE = 1, 2, 3


def measure(s, size, fam=VIRGIL):
    longest = max(s.split("\n"), key=len)
    return (int(len(longest) * size * CH[fam] * PAD),
            int(len(s.split("\n")) * size * 1.25))


# ------------------------------------------------------------------- elements

def _seed(eid):
    """Deterministic seed — roughness renders the same on every run."""
    return int(hashlib.sha1(eid.encode()).hexdigest()[:8], 16)


def base(eid, etype, x, y, w, h, stroke="#1e1e1e", bg="transparent", **kw):
    e = {
        "id": eid, "type": etype,
        "x": round(x, 2), "y": round(y, 2),
        "width": round(w, 2), "height": round(h, 2),
        "angle": 0,
        "strokeColor": stroke, "backgroundColor": bg,
        "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
        "roughness": 1, "opacity": 100,
        "groupIds": [], "frameId": None, "roundness": None,
        "seed": _seed(eid), "version": 1, "versionNonce": _seed(eid + "n"),
        "isDeleted": False, "boundElements": [], "updated": 1,
        "link": None, "locked": False,
    }
    e.update(kw)
    return e


def rect(eid, x, y, w, h, stroke="#1e1e1e", bg="transparent", radius=True, **kw):
    return base(eid, "rectangle", x, y, w, h, stroke=stroke, bg=bg,
                roundness={"type": 3} if radius else None, **kw)


def ellipse(eid, x, y, w, h, stroke="#1e1e1e", bg="transparent", **kw):
    return base(eid, "ellipse", x, y, w, h, stroke=stroke, bg=bg, **kw)


def txt(eid, x, y, s, size=16, color="#1e1e1e", fam=VIRGIL, center_in=None):
    """center_in = (box_x, box_w) centres the measured text inside that box."""
    w, h = measure(s, size, fam)
    if center_in:
        bx, bw = center_in
        x = bx + (bw - w) / 2
    return base(eid, "text", x, y, w, h, stroke=color, text=s, fontSize=size,
                fontFamily=fam, textAlign="center" if center_in else "left",
                verticalAlign="top", containerId=None, originalText=s,
                lineHeight=1.25, autoResize=True)


def arrow(eid, x, y, dx, dy=0, color="#1e1e1e", curved=True, **kw):
    return base(eid, "arrow", x, y, dx, dy, stroke=color,
                points=[[0, 0], [dx, dy]], lastCommittedPoint=None,
                startBinding=None, endBinding=None,
                startArrowhead=None, endArrowhead="arrow",
                roundness={"type": 2} if curved else None,
                elbowed=False, **kw)


def line(eid, x, y, dx, dy=0, color="#1e1e1e", style="solid"):
    return base(eid, "line", x, y, dx, dy, stroke=color, strokeStyle=style,
                points=[[0, 0], [dx, dy]], lastCommittedPoint=None,
                startBinding=None, endBinding=None,
                startArrowhead=None, endArrowhead=None, roundness=None)


# ----------------------------------------------------------------- the board

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml"}


def image_size(path):
    """(width, height) of an image without embedding it — lets a layout size its
    slot to the art instead of letterboxing a 16:9 render into a 2:1 hole."""
    from PIL import Image
    with Image.open(path) as im:
        return im.size


class Board:
    """Accumulates elements and embedded image files, then writes one .excalidraw."""

    def __init__(self, background="#ffffff"):
        self.elements = []
        self.files = {}
        self.background = background

    def add(self, *els):
        for e in els:
            self.elements.append(e)
        return els[-1] if len(els) == 1 else els

    def group(self, group_id, els):
        """Tie elements together so a click selects the whole panel."""
        for e in els:
            e["groupIds"] = [group_id] + e.get("groupIds", [])
        return els

    # -- the embed step -----------------------------------------------------

    def embed_image(self, eid, path, x, y, box_w, box_h,
                    max_px=1400, fit="contain", optimize=True):
        """Embed `path` into the file and place it inside (x, y, box_w, box_h).

        The image is downscaled so its longest side is at most `max_px` before
        being base64'd. Skipping this is how a five-panel board becomes a 45MB
        file that Excalidraw takes ten seconds to open — a 2752px illustration
        rendered in a 420px panel carries six times the pixels it can show.

        fit="contain" preserves aspect ratio inside the box (letterboxed and
        centred). fit="stretch" fills the box exactly.

        Returns the image element, already added to the board.
        """
        p = pathlib.Path(path)
        raw = p.read_bytes()
        suffix = p.suffix.lower()
        mime = MIME.get(suffix)
        if mime is None:
            raise ValueError(f"unsupported image type: {suffix}")

        if suffix == ".svg":
            data, iw, ih = raw, box_w, box_h
        else:
            data, iw, ih = _downscale(raw, mime, max_px, optimize)

        file_id = hashlib.sha1(data).hexdigest()
        if file_id not in self.files:
            # Deterministic timestamp: same bytes -> same file, every run.
            stamp = int(file_id[:10], 16) % 1_000_000_000 + 1_600_000_000_000
            self.files[file_id] = {
                "mimeType": mime,
                "id": file_id,
                "dataURL": f"data:{mime};base64,{base64.b64encode(data).decode()}",
                "created": stamp,
                "lastRetrieved": stamp,
            }

        if fit == "contain":
            scale = min(box_w / iw, box_h / ih)
            w, h = iw * scale, ih * scale
            px, py = x + (box_w - w) / 2, y + (box_h - h) / 2
        else:
            w, h, px, py = box_w, box_h, x, y

        el = base(eid, "image", px, py, w, h,
                  stroke="transparent", bg="transparent",
                  fileId=file_id, status="saved", scale=[1, 1], crop=None)
        self.elements.append(el)
        return el

    # -- output -------------------------------------------------------------

    def to_dict(self):
        return {
            "type": "excalidraw", "version": 2,
            "source": "https://excalidraw.com",
            "elements": self.elements,
            "appState": {"gridSize": None, "viewBackgroundColor": self.background},
            "files": self.files,
        }

    def save(self, path):
        out = pathlib.Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), indent=2))
        mb = out.stat().st_size / 1_048_576
        print(f"wrote {out}  —  {len(self.elements)} elements, "
              f"{len(self.files)} embedded image(s), {mb:.1f} MB")
        if mb > 20:
            print("  WARNING: over 20MB. Excalidraw will be slow to open this. "
                  "Lower max_px on embed_image().")
        return out


def _downscale(raw, mime, max_px, optimize):
    """Return (bytes, width, height), shrunk so the longest side <= max_px."""
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    iw, ih = im.size
    longest = max(iw, ih)
    if longest <= max_px and not optimize:
        return raw, iw, ih
    if longest > max_px:
        k = max_px / longest
        im = im.resize((max(1, round(iw * k)), max(1, round(ih * k))),
                       Image.LANCZOS)
    buf = io.BytesIO()
    if mime == "image/jpeg":
        im.convert("RGB").save(buf, "JPEG", quality=88, optimize=True)
    else:
        # Line art and flat colour: a palette shrinks these hard with no visible
        # loss. Photographic panels keep full colour.
        if im.mode in ("RGBA", "LA"):
            im.save(buf, "PNG", optimize=True)
        else:
            im.convert("RGB").save(buf, "PNG", optimize=True)
    data = buf.getvalue()
    return (data, im.size[0], im.size[1]) if len(data) < len(raw) or longest > max_px \
        else (raw, iw, ih)
