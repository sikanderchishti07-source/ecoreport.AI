# -*- coding: utf-8 -*-
"""Bake computed numbers into Word field caches after rendering.

Why this exists
---------------
A Word field stores two things: the instruction (``SEQ Table \\* ARABIC``) and
a cached result — the text a reader displays when it does not evaluate the
instruction itself.

Word evaluates fields. LibreOffice, which produces our PDFs, does not. The
template wrote an empty cache, so every exported PDF read::

    Table  — Summary of SO2 Results
    Figure  — SO2 Hourly Concentration at the location.

This module walks the rendered document in reading order, counts the captions
the way Word would, and writes the numbers into the caches. The fields stay
live, so Word still renumbers on its own if the document is edited — but the
document is now correct before Word ever opens it, and therefore correct in
the PDF too.

Run this after ``DocxTemplate.render()``, never before: rendering is what
expands the Jinja loops (calibration certificates, licence pages), and those
loops change how many captions the document actually contains.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import zipfile
from typing import Dict

log = logging.getLogger(__name__)

DOC_XML = "word/document.xml"

# One field = one run holding: begin, instrText, separate, cached result, end.
_FIELD_RE = re.compile(
    r'(<w:fldChar\s+w:fldCharType="begin"\s*/>'
    r'<w:instrText[^>]*>)(.*?)(</w:instrText>'
    r'<w:fldChar\s+w:fldCharType="separate"\s*/>)'
    r'<w:t[^>]*>[^<]*</w:t>'
    r'(<w:fldChar\s+w:fldCharType="end"\s*/>)',
    re.S,
)

_SEQ_RE = re.compile(r"\bSEQ\s+(\w+)", re.I)


def _populate(xml: str) -> tuple[str, Dict[str, int]]:
    """Rewrite every SEQ field's cached result with its computed number."""
    counters: Dict[str, int] = {}
    out = []
    last = 0

    for m in _FIELD_RE.finditer(xml):
        instr = m.group(2)
        seq = _SEQ_RE.search(instr)
        if not seq:
            continue                      # TOC / PAGE / STYLEREF: leave alone
        kind = seq.group(1)
        counters[kind] = counters.get(kind, 0) + 1
        out.append(xml[last:m.start()])
        out.append(
            m.group(1) + instr + m.group(3)
            + "<w:t>%d</w:t>" % counters[kind]
            + m.group(4)
        )
        last = m.end()

    out.append(xml[last:])
    return "".join(out), counters


def populate_field_caches(docx_path: str) -> Dict[str, int]:
    """Rewrite caption numbers in place. Returns {"Table": n, "Figure": n}.

    Never raises: a report that ships with blank caption numbers is a defect,
    but a report that fails to ship at all is worse.
    """
    try:
        with zipfile.ZipFile(docx_path) as zin:
            names = zin.namelist()
            if DOC_XML not in names:
                log.warning("%s has no %s — skipped", docx_path, DOC_XML)
                return {}
            blobs = {n: zin.read(n) for n in names}

        xml = blobs[DOC_XML].decode("utf-8")
        fixed, counters = _populate(xml)
        if not counters:
            return {}
        blobs[DOC_XML] = fixed.encode("utf-8")

        fd, tmp = tempfile.mkstemp(suffix=".docx",
                                   dir=os.path.dirname(os.path.abspath(docx_path)))
        os.close(fd)
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for n in names:               # preserve original entry order
                zout.writestr(n, blobs[n])
        shutil.move(tmp, docx_path)

        log.info("caption numbers written: %s",
                 ", ".join(f"{k} 1-{v}" for k, v in sorted(counters.items())))
        return counters
    except Exception:  # noqa: BLE001
        log.exception("field cache population failed — captions may be blank")
        return {}
