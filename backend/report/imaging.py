# -*- coding: utf-8 -*-
"""Shrink photographic images on their way into the document.

A finished report was carrying 30 MB of images for 8 MB of content. The
dimensions were never the problem — most were already around 1000-1500 px.
The problem was the format: satellite tiles, the cover photograph and every
scanned calibration certificate were stored as PNG, which is lossless and
therefore hopeless at photographs. A certificate page cost 1.3 MB as PNG and
0.24 MB as JPEG at a quality no one can distinguish on paper.

``slim`` is called once per image as it is placed in the document, so it fixes
campaigns whose files were uploaded long before this existed. The original on
disk is never modified; a converted copy is written beside the charts and
thrown away with them.

What is deliberately left alone
-------------------------------
* **Brand artwork** — anything under ``report/assets``: the logo, the
  accreditation badges, the watermark. Small, sharp-edged, and on the cover.
* **Anything using transparency.** JPEG has no alpha channel; converting the
  watermark would paint a white box over the page.
* **Flat-colour images.** Charts, diagrams and logos have a countable number
  of colours. JPEG rings around thin lines and small text, and there is
  nothing to gain: the charts are 60-100 KB each already.
* **Small files**, under ``MIN_BYTES``. Not worth the CPU or the risk.
* Anything where the JPEG comes out no smaller than the original.

Failure is never fatal: on any error the original path is returned and the
report is built exactly as before, only larger.
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

MAX_PX = 1600          # longest side; 150 mm wide on the page is ~270 dpi
QUALITY = 85           # visually lossless for photographs and scans
MIN_BYTES = 400_000    # below this, leave it alone
MAX_COLOURS = 20_000   # more unique colours than this counts as photographic

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _uses_transparency(im) -> bool:
    """True when the alpha channel actually does something. Matplotlib writes
    RGBA even for fully opaque figures, so the mode alone proves nothing."""
    if im.mode == "P":
        im = im.convert("RGBA")
    if im.mode not in ("RGBA", "LA"):
        return False
    return im.getchannel("A").getextrema()[0] < 250


def _is_flat(im) -> bool:
    """True for charts, diagrams and logos — few distinct colours."""
    return im.getcolors(maxcolors=MAX_COLOURS) is not None


def _cache_path(src: str, work_dir: str) -> str:
    st = os.stat(src)
    key = "%s|%d|%d" % (os.path.abspath(src), st.st_size, int(st.st_mtime))
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return os.path.join(work_dir, "_slim", digest + ".jpg")


def slim(path: Optional[str], work_dir: Optional[str],
         max_px: int = MAX_PX, quality: int = QUALITY) -> Optional[str]:
    """Return a path to a smaller copy, or the original when it is best left."""
    if not path or not work_dir or not os.path.exists(path):
        return path
    try:
        if os.path.abspath(path).startswith(ASSETS_DIR + os.sep):
            return path                       # brand artwork
        size = os.path.getsize(path)
        if size < MIN_BYTES:
            return path

        cached = _cache_path(path, work_dir)
        if os.path.exists(cached):
            return cached

        from PIL import Image, ImageOps

        with Image.open(path) as im:
            im.load()
            if _uses_transparency(im):
                return path
            if _is_flat(im):
                return path
            # Phone photographs record their orientation in EXIF and Word
            # ignores it; bake the rotation into the pixels so a re-encoded
            # photo cannot come out sideways.
            im = ImageOps.exif_transpose(im)
            w, h = im.size
            scale = min(1.0, float(max_px) / max(w, h))
            if scale < 1.0:
                im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                               Image.LANCZOS)
            os.makedirs(os.path.dirname(cached), exist_ok=True)
            im.convert("RGB").save(cached, "JPEG", quality=quality,
                                   optimize=True, progressive=True)

        if os.path.getsize(cached) >= size:
            os.remove(cached)                 # nothing gained
            return path
        log.debug("slimmed %s: %d -> %d bytes",
                  os.path.basename(path), size, os.path.getsize(cached))
        return cached
    except Exception:  # noqa: BLE001
        log.warning("could not slim %s — using the original",
                    os.path.basename(str(path)), exc_info=True)
        return path
