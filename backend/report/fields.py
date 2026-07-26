# -*- coding: utf-8 -*-
"""Write the report's own numbers into the document instead of asking Word.

Two jobs, both run after ``DocxTemplate.render()``:

``populate_field_caches``
    Fills each caption's SEQ field cache, so "Table 7 — Summary of SO2
    Results" reads correctly everywhere.

``build_indexes``
    Replaces the three index fields (Table of Contents, List of Figures,
    List of Tables) with real entries carrying real page numbers.

Why not leave it to Word
------------------------
A Word field stores an instruction and a cached result. Word evaluates the
instruction; LibreOffice — which produces our PDFs — never does. The template
wrote empty caches, so every exported PDF carried three blank index pages and
37 captions reading "Table  —".

Marking the fields dirty does not help: LibreOffice ignores that too. Nor does
``w:updateFields``, which Word honours only at open time, before the document
has been paginated — which is why the contents page showed 1 against every
entry. So the numbers are computed here and written in as literal text. The
document is then correct in Word, in LibreOffice, and in a phone PDF viewer,
without depending on the reader to finish the job.

Page numbers need a layout pass, so ``build_indexes`` converts the document
once to find out where everything landed. The entries are inserted *before*
that conversion with their numbers left blank, so the index pages are already
at full height when pagination is measured; filling in a two-digit number
afterwards cannot push anything onto a different page.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

DOC_XML = "word/document.xml"
SETTINGS_XML = "word/settings.xml"

# One field = one run: begin, instrText, separate, cached result, end.
_FIELD_RE = re.compile(
    r'(<w:fldChar\s+w:fldCharType="begin"[^/]*/>'
    r'<w:instrText[^>]*>)(.*?)(</w:instrText>'
    r'<w:fldChar\s+w:fldCharType="separate"\s*/>)'
    r'<w:t[^>]*>[^<]*</w:t>'
    r'(<w:fldChar\s+w:fldCharType="end"\s*/>)',
    re.S,
)
_SEQ_RE = re.compile(r"\bSEQ\s+(\w+)", re.I)

INDEX_TITLES = ("Table of Contents", "List of Figures", "List of Tables")


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------
def _rewrite_zip(path: str, names: List[str], blobs: Dict[str, bytes]) -> None:
    fd, tmp = tempfile.mkstemp(suffix=".docx",
                               dir=os.path.dirname(os.path.abspath(path)))
    os.close(fd)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in names:                    # preserve original entry order
            zout.writestr(n, blobs[n])
    shutil.move(tmp, path)


def _norm(text: str) -> str:
    """Collapse whitespace and drop soft hyphens so PDF text and document text
    compare equal even where the layout engine has rewrapped a line."""
    return re.sub(r"\s+", " ", (text or "").replace("\u00ad", "")).strip()


# ---------------------------------------------------------------------------
# 1. Caption numbers
# ---------------------------------------------------------------------------
def _populate(xml: str) -> Tuple[str, Dict[str, int]]:
    counters: Dict[str, int] = {}
    out: List[str] = []
    last = 0
    for m in _FIELD_RE.finditer(xml):
        instr = m.group(2)
        seq = _SEQ_RE.search(instr)
        if not seq:
            continue                       # TOC / PAGE: handled elsewhere
        kind = seq.group(1)
        counters[kind] = counters.get(kind, 0) + 1
        out.append(xml[last:m.start()])
        out.append(m.group(1) + instr + m.group(3)
                   + "<w:t>%d</w:t>" % counters[kind] + m.group(4))
        last = m.end()
    out.append(xml[last:])
    return "".join(out), counters


def populate_field_caches(docx_path: str) -> Dict[str, int]:
    """Write computed caption numbers into their field caches, in place."""
    try:
        with zipfile.ZipFile(docx_path) as zin:
            names = zin.namelist()
            if DOC_XML not in names:
                return {}
            blobs = {n: zin.read(n) for n in names}

        fixed, counters = _populate(blobs[DOC_XML].decode("utf-8"))
        if not counters:
            return {}
        blobs[DOC_XML] = fixed.encode("utf-8")
        _rewrite_zip(docx_path, names, blobs)
        log.info("caption numbers written: %s",
                 ", ".join(f"{k} 1-{v}" for k, v in sorted(counters.items())))
        return counters
    except Exception:  # noqa: BLE001
        log.exception("caption numbering failed — captions may be blank")
        return {}


# ---------------------------------------------------------------------------
# 2. Index pages
# ---------------------------------------------------------------------------
def _pdf_pages(pdf_path: str) -> List[str]:
    """Per-page plain text. PyMuPDF is already a dependency; pdftotext is the
    fallback for hosts where it cannot be imported."""
    try:
        import fitz                        # PyMuPDF
        with fitz.open(pdf_path) as doc:
            return [p.get_text() for p in doc]
    except Exception:  # noqa: BLE001
        log.info("PyMuPDF unavailable — falling back to pdftotext")
    try:
        out = subprocess.run(["pdftotext", "-layout", pdf_path, "-"],
                             capture_output=True, timeout=180, check=True)
        return out.stdout.decode("utf-8", "replace").split("\f")
    except Exception:  # noqa: BLE001
        log.exception("could not read page text from %s", pdf_path)
        return []


def _page_lookup(pages: List[str]) -> Tuple[List[str], set]:
    """Normalised page text, plus the indices of the index pages themselves.

    Those pages repeat every heading and caption verbatim, so they must be
    excluded or every entry would resolve to the contents page. Detection is
    by dot leaders rather than by title, so it works just as well on the
    Arabic half of a bilingual report.
    """
    norm = [_norm(p) for p in pages]
    skip = set()
    for i, (raw, t) in enumerate(zip(pages, norm)):
        if any(title in t for title in INDEX_TITLES):
            skip.add(i)
        elif raw.count("....") >= 5:          # a page of dot-leader entries
            skip.add(i)
    return norm, skip


def _find_page(norm_pages: List[str], skip: set, text: str) -> Optional[int]:
    needle = _norm(text)
    if not needle:
        return None
    for i, page in enumerate(norm_pages):
        if i not in skip and needle in page:
            return i + 1
    # Long captions sometimes wrap awkwardly; retry on a distinctive prefix.
    short = " ".join(needle.split()[:6])
    if len(short) >= 12:
        for i, page in enumerate(norm_pages):
            if i not in skip and short in page:
                return i + 1
    return None


def _plan(doc) -> List[Tuple[object, List[Tuple[int, str]]]]:
    """Pair every index anchor with the entries that belong to it.

    A bilingual report contains the whole English document followed by the
    whole Arabic one, so there are two Tables of Contents, two Lists of
    Figures and two Lists of Tables. Walking the document once and assigning
    each heading or caption to the most recent anchor of its kind keeps each
    index describing its own half, instead of the English index absorbing the
    Arabic captions as well.
    """
    buckets: Dict[int, List[Tuple[int, str]]] = {}
    order: List[object] = []
    current: Dict[str, object] = {"toc": None, "fig": None, "tab": None}

    def _open(kind: str, paragraph) -> None:
        current[kind] = paragraph
        buckets[id(paragraph)] = []
        order.append(paragraph)

    for p in doc.paragraphs:
        xml = p._p.xml
        if "instrText" in xml and "TOC" in xml:
            if "\\o" in xml:
                _open("toc", p)
            elif "Figure" in xml:
                _open("fig", p)
            elif "Table" in xml:
                _open("tab", p)
            continue

        text = (p.text or "").strip()
        if not text:
            continue
        style = (p.style.name or "") if p.style is not None else ""

        if style.startswith("Heading"):
            if text in INDEX_TITLES:
                continue
            anchor = current["toc"]
            if anchor is None:
                continue
            m = re.search(r"(\d)", style)
            level = int(m.group(1)) if m else 1
            if level <= 3:
                buckets[id(anchor)].append((level, text))
        elif style == "Caption":
            kind = "fig" if text.startswith("Figure") else (
                "tab" if text.startswith("Table") else None)
            if kind is None:
                continue
            anchor = current[kind]
            if anchor is not None:
                buckets[id(anchor)].append((1, text))

    return [(a, buckets[id(a)]) for a in order if buckets[id(a)]]


def _entry(doc, level: int, text: str, right_tab_in: float):
    """One index line: text, dot leader, right-aligned page number."""
    from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
    from docx.shared import Inches, Pt

    p = doc.add_paragraph()                # appended, then moved into place
    pf = p.paragraph_format
    pf.left_indent = Inches(0.24 * (level - 1))
    pf.space_after = Pt(3)
    pf.tab_stops.add_tab_stop(Inches(right_tab_in), WD_TAB_ALIGNMENT.RIGHT,
                              WD_TAB_LEADER.DOTS)
    run = p.add_run(text)
    run.font.size = Pt(10)
    page_run = p.add_run("\t")             # number filled in after measuring
    page_run.font.size = Pt(10)
    return p, page_run


def _insert_after(anchor, paragraphs) -> None:
    """Place paragraphs directly after the anchor, keeping their order."""
    for p in reversed(paragraphs):
        anchor._p.addnext(p._p)


def _strip_field(paragraph) -> None:
    """Remove the now-redundant TOC field so Word cannot regenerate a second,
    duplicate index on top of the one we just wrote."""
    for run in list(paragraph.runs):
        if "fldChar" in run._r.xml or "instrText" in run._r.xml:
            run._r.getparent().remove(run._r)


def _disable_update_on_open(docx_path: str) -> None:
    """Drop <w:updateFields/>. Every number in the document is now literal, so
    an update on open can only replace correct values with Word's own — which
    is what produced a contents page reading 1 against every entry."""
    try:
        with zipfile.ZipFile(docx_path) as zin:
            names = zin.namelist()
            blobs = {n: zin.read(n) for n in names}
        if SETTINGS_XML not in blobs:
            return
        settings = blobs[SETTINGS_XML].decode("utf-8")
        cleaned = re.sub(r"<w:updateFields[^/]*/>", "", settings)
        if cleaned != settings:
            blobs[SETTINGS_XML] = cleaned.encode("utf-8")
            _rewrite_zip(docx_path, names, blobs)
    except Exception:  # noqa: BLE001
        log.exception("could not clear updateFields")


def build_indexes(docx_path: str, convert_to_pdf) -> bool:
    """Populate the three index pages with real entries and page numbers.

    ``convert_to_pdf(docx_path, out_dir) -> pdf_path`` is passed in rather
    than imported, so this module stays independent of the report package's
    conversion strategy.

    Returns True when page numbers were resolved. On any failure the document
    still keeps its entries — an index without page numbers is a great deal
    better than three blank pages.
    """
    try:
        from docx import Document

        doc = Document(docx_path)
        plan = _plan(doc)
        if not plan:
            log.warning("no headings or captions found — indexes left empty")
            return False

        # Length arithmetic returns a plain int (EMU) in python-docx, so the
        # conversion to inches is done explicitly. The first section can carry
        # zero margins (the cover is laid out full-bleed), which would push the
        # tab stop past the printable area and wrap every page number onto its
        # own line — so use the widest sensible margin defined anywhere.
        EMU_IN = 914400.0
        usable = []
        for sec in doc.sections:
            width = int(sec.page_width or 0)
            left = int(sec.left_margin or 0)
            right = int(sec.right_margin or 0)
            if width and left and right:
                usable.append((width - left - right) / EMU_IN)
        if usable:
            right_tab = min(usable)
        else:
            page_in = int(doc.sections[0].page_width or 0) / EMU_IN or 8.27
            right_tab = page_in - 2.0       # assume 1" margins
        right_tab = max(right_tab, 2.0)

        page_runs: List[Tuple[object, str]] = []
        for anchor, entries in plan:
            built = []
            for level, text in entries:
                p, run = _entry(doc, level, text, right_tab)
                built.append(p)
                page_runs.append((run, text))
            _insert_after(anchor, built)
            _strip_field(anchor)

        doc.save(docx_path)                # entries present, numbers blank

        # Measure. The index pages are already at full height, so the page a
        # heading falls on cannot move when its number is filled in.
        with tempfile.TemporaryDirectory(prefix="ecoreport_idx_") as td:
            probe = os.path.join(td, "probe.docx")
            shutil.copy(docx_path, probe)
            try:
                pdf = convert_to_pdf(probe, td)
            except Exception:  # noqa: BLE001
                log.exception("index measuring pass failed — "
                              "entries kept without page numbers")
                _disable_update_on_open(docx_path)
                return False
            norm_pages, skip = _page_lookup(_pdf_pages(pdf))

        if not norm_pages:
            _disable_update_on_open(docx_path)
            return False

        resolved = 0
        for run, text in page_runs:
            page = _find_page(norm_pages, skip, text)
            if page:
                run.text = "\t%d" % page
                resolved += 1

        doc.save(docx_path)
        _disable_update_on_open(docx_path)
        log.info("indexes built: %d index block(s), %d entries, "
                 "%d/%d page numbers resolved",
                 len(plan), len(page_runs), resolved, len(page_runs))
        return resolved > 0
    except Exception:  # noqa: BLE001
        log.exception("index build failed — index pages may be empty")
        return False
