#!/usr/bin/env python3
"""Structural check on a .excalidraw file before anyone opens it.

    python3 verify_board.py <file.excalidraw>

Catches the failures that make a board look fine in a screenshot and broken on
import: an image element pointing at a fileId that was never written, a dataURL
that does not decode, a stated width/height that does not match the embedded
pixels (which squashes the art), and text wider than the box it sits in.

This is structure only. It cannot tell you whether the drawing is any good, and
it deliberately does not screenshot the local canvas — that canvas mis-renders
text and will send you chasing faults that are not in the file.
"""

import base64
import io
import json
import pathlib
import sys


def verify(path):
    doc = json.loads(pathlib.Path(path).read_text())
    els = doc.get("elements", [])
    files = doc.get("files", {})
    problems, notes = [], []

    images = [e for e in els if e.get("type") == "image"]

    for e in images:
        fid = e.get("fileId")
        if fid not in files:
            problems.append(f"image {e['id']}: fileId {fid} missing from files map")
            continue
        if e.get("status") != "saved":
            problems.append(f"image {e['id']}: status is {e.get('status')!r}, "
                            "must be 'saved' or Excalidraw shows an empty frame")
        url = files[fid].get("dataURL", "")
        if not url.startswith("data:"):
            problems.append(f"file {fid}: dataURL is not a data: URI")
            continue
        try:
            raw = base64.b64decode(url.split(",", 1)[1])
        except Exception as exc:
            problems.append(f"file {fid}: base64 will not decode ({exc})")
            continue
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(raw))
            im.verify()
            iw, ih = im.size
        except Exception as exc:
            problems.append(f"file {fid}: not a readable image ({exc})")
            continue

        ew, eh = e["width"], e["height"]
        if ew <= 0 or eh <= 0:
            problems.append(f"image {e['id']}: zero-sized element")
            continue
        skew = abs((ew / eh) / (iw / ih) - 1)
        if skew > 0.02:
            problems.append(f"image {e['id']}: element is {ew:.0f}x{eh:.0f} but the "
                            f"picture is {iw}x{ih} — art is stretched by {skew:.0%}")

    for fid in files:
        if not any(e.get("fileId") == fid for e in images):
            notes.append(f"file {fid[:8]}… is embedded but no element uses it "
                         "(dead weight in the file size)")

    # Text overflow: Excalidraw clips to the stored width on import rather than
    # re-measuring, so a too-narrow text element silently loses characters.
    for e in els:
        if e.get("type") == "text":
            longest = max(e.get("text", "").split("\n"), key=len, default="")
            need = len(longest) * e.get("fontSize", 16) * 0.62
            if e["width"] < need * 0.9:
                notes.append(f"text {e['id']}: width {e['width']:.0f} may clip "
                             f"{longest[:40]!r}")

    size_mb = pathlib.Path(path).stat().st_size / 1_048_576
    print(f"{path}")
    print(f"  {len(els)} elements · {len(images)} image element(s) · "
          f"{len(files)} embedded file(s) · {size_mb:.1f} MB")
    for n in notes:
        print(f"  note:    {n}")
    for p in problems:
        print(f"  PROBLEM: {p}")
    if not problems:
        print("  structure OK")
    return len(problems)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(min(1, sum(verify(a) for a in sys.argv[1:])))
