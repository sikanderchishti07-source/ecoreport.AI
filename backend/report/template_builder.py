"""Builds the master docxtpl template (master_template.docx) programmatically.

The template replicates the BSA gold-standard AAQ report structure:
cover, document control, TOC/LoF/LoT, definitions, executive summary,
sections 1-6, appendices — with Jinja placeholders for everything dynamic.

Rebuild any time with:  python -m report.template_builder
"""
from __future__ import annotations

import os

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
OUT = os.path.join(os.path.dirname(__file__), "master_template.docx")

# Brand palette — blue-dominant with a restrained green accent
NAVY = RGBColor(0x0F, 0x3D, 0x6E)
BLUE = RGBColor(0x1F, 0x6F, 0xB2)
GREEN = RGBColor(0x2F, 0x9E, 0x63)
DARK = RGBColor(0x1F, 0x1F, 0x1F)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
NAVY_FILL = "0F3D6E"
BLUE_FILL = "1F6FB2"
SKY_FILL = "E8F1F9"
GREEN_ACCENT = RGBColor(0x2F, 0x7D, 0x32)
MUTED_GREY = RGBColor(0x6B, 0x6B, 0x6B)
GRAY_FILL = NAVY_FILL   # legacy alias: all header cells now use the navy fill
_DARK_FILLS = {NAVY_FILL, BLUE_FILL}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------
def _field(paragraph, instr: str):
    """Insert a Word field (TOC, PAGE, SEQ...) into a paragraph."""
    r = paragraph.add_run()
    for el, attrs, text in (
        ("w:fldChar", {"w:fldCharType": "begin"}, None),
        ("w:instrText", {"xml:space": "preserve"}, instr),
        ("w:fldChar", {"w:fldCharType": "separate"}, None),
        ("w:t", {}, " "),
        ("w:fldChar", {"w:fldCharType": "end"}, None),
    ):
        e = OxmlElement(el)
        for k, v in attrs.items():
            e.set(qn(k), v)
        if text is not None:
            e.text = text
        r._r.append(e)


def _update_fields_on_open(doc):
    settings = doc.settings.element
    upd = OxmlElement("w:updateFields")
    upd.set(qn("w:val"), "true")
    settings.append(upd)


def _shade(cell, fill=GRAY_FILL):
    if fill in _DARK_FILLS:
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.color.rgb = WHITE
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def _cell_text(cell, text, bold=False, size=10, align="left", italic=False):
    cell.paragraphs[0].text = ""
    p = cell.paragraphs[0]
    p.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT,
                   "center": WD_ALIGN_PARAGRAPH.CENTER,
                   "right": WD_ALIGN_PARAGRAPH.RIGHT}[align]
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    return cell


def _merge_row(table, row_idx, start, end):
    a = table.cell(row_idx, start)
    b = table.cell(row_idx, end)
    a.merge(b)
    return a


def _p(doc, text="", size=11, bold=False, italic=False, align="left",
       style=None, space_after=6, color=None):
    p = doc.add_paragraph(style=style)
    p.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT,
                   "center": WD_ALIGN_PARAGRAPH.CENTER,
                   "right": WD_ALIGN_PARAGRAPH.RIGHT,
                   "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}[align]
    p.paragraph_format.space_after = Pt(space_after)
    if text:
        r = p.add_run(text)
        r.bold = bold
        r.italic = italic
        r.font.size = Pt(size)
        if color:
            r.font.color.rgb = color
    return p


def _heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    for r in h.runs:
        r.font.color.rgb = DARK
    return h


def _caption(doc, kind: str, text: str):
    """'Table 6: Summary...' with SEQ auto-numbering so LoF/LoT fields work."""
    p = doc.add_paragraph(style="Caption")
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run(f"{kind} ")
    r.bold = True
    _field(p, f" SEQ {kind} \\* ARABIC ")
    for run in p.runs:
        run.font.color.rgb = NAVY
        run.font.size = Pt(10)
        run.bold = True
        run.italic = False
    r2 = p.add_run(f": {text}")
    r2.bold = True
    r2.font.size = Pt(10)
    r2.font.color.rgb = DARK
    return p


def _summary_table(doc, rows, ncec_cols):
    """Gold-standard pollutant summary table.
    rows: list of (label, value_placeholder) tuples.
    ncec_cols: list of (period_label, limit_placeholder)."""
    n_ncec = max(len(ncec_cols), 1)
    tbl = doc.add_table(rows=2 + len(rows), cols=2 + n_ncec)
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    # Header row 0: descriptor merged | "NCEC Exceedance Level µg/m³" merged
    _merge_row(tbl, 0, 0, 1)
    _cell_text(tbl.cell(0, 0), "", size=10)
    hdr = tbl.cell(0, 2)
    if n_ncec > 1:
        hdr = _merge_row(tbl, 0, 2, 1 + n_ncec)
    _cell_text(hdr, "NCEC Exceedance Level µg/m³", bold=True, size=10, align="center")
    _shade(hdr)
    # Header row 1: blank | blank | period labels
    _merge_row(tbl, 1, 0, 1)
    for j, (period, _) in enumerate(ncec_cols):
        _cell_text(tbl.cell(1, 2 + j), period, bold=True, size=10, align="center")
        _shade(tbl.cell(1, 2 + j))
    # Data rows; NCEC limit cells merged vertically across all data rows
    for i, (label, value) in enumerate(rows):
        _cell_text(tbl.cell(2 + i, 0), label, size=10)
        _cell_text(tbl.cell(2 + i, 1), value, size=10, align="center")
    for j, (_, limit_ph) in enumerate(ncec_cols):
        top = tbl.cell(2, 2 + j)
        bottom = tbl.cell(1 + len(rows), 2 + j)
        merged = top.merge(bottom)
        _cell_text(merged, limit_ph, size=10, align="center")
    return tbl


def _tr_tag_row(table, row_idx, tag):
    """A dedicated row containing only a {%tr %} tag (docxtpl removes the row)."""
    cell = table.cell(row_idx, 0)
    cell.paragraphs[0].text = tag


def _header_footer(section):
    """Two-logo header with centered italic title; footer with page number."""
    hdr = section.header
    hdr.is_linked_to_previous = False
    tbl = hdr.add_table(rows=1, cols=3, width=Cm(17))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    left, mid, right = tbl.rows[0].cells
    lp = left.paragraphs[0]
    lp.alignment = WD_ALIGN_PARAGRAPH.LEFT
    try:
        lp.add_run().add_picture(os.path.join(ASSETS, "logo_left.png"), height=Cm(1.6))
    except Exception:
        lp.add_run("[BSA]")
    mp = mid.paragraphs[0]
    mp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r1 = mp.add_run("Ambient Air Quality Monitoring Report for")
    r1.italic = True
    r1.bold = True
    r1.font.size = Pt(10)
    r1.font.color.rgb = NAVY
    r1.font.size = Pt(9.5)
    mp2 = mid.add_paragraph()
    mp2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = mp2.add_run("{{ project_name }}")
    r2.italic = True
    r2.bold = True
    r2.font.size = Pt(10)
    r2.font.color.rgb = NAVY
    r2.font.size = Pt(9.5)
    rp = right.paragraphs[0]
    rp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    try:
        rp.add_run().add_picture(os.path.join(ASSETS, "logo_right.png"), height=Cm(1.6))
    except Exception:
        rp.add_run("[LOGO]")
    # bottom rule under the header
    rule = hdr.add_paragraph()
    pPr = rule._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bot = OxmlElement("w:bottom")
    bot.set(qn("w:val"), "single")
    bot.set(qn("w:sz"), "14")
    bot.set(qn("w:color"), BLUE_FILL)
    borders.append(bot)
    pPr.append(borders)

    ftr = section.footer
    ftr.is_linked_to_previous = False
    fp = ftr.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fPr = fp._p.get_or_add_pPr()
    fBdr = OxmlElement("w:pBdr")
    ftop = OxmlElement("w:top")
    ftop.set(qn("w:val"), "single")
    ftop.set(qn("w:sz"), "8")
    ftop.set(qn("w:color"), NAVY_FILL)
    fBdr.append(ftop)
    fPr.append(fBdr)
    pre = fp.add_run("Page ")
    pre.font.size = Pt(9)
    pre.font.color.rgb = NAVY
    _field(fp, " PAGE ")
    for r in fp.runs:
        r.font.size = Pt(9)
        r.font.color.rgb = NAVY


# ---------------------------------------------------------------------------
# Document assembly
# ---------------------------------------------------------------------------

def _modernise_settings(doc):
    """Drop the legacy compatibility flag and force field update on open, so
    Word populates the Table of Contents / List of Figures / List of Tables
    without the reader pressing Ctrl+A F9."""
    settings = doc.settings.element
    for tag in ("w:compat",):
        el = settings.find(qn(tag))
        if el is not None:
            settings.remove(el)
    if settings.find(qn("w:updateFields")) is None:
        uf = OxmlElement("w:updateFields")
        uf.set(qn("w:val"), "true")
        settings.append(uf)


def build(out_path: str = OUT) -> str:
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(11)
    for lvl in range(1, 4):
        hs = doc.styles[f"Heading {lvl}"]
        hs.font.name = "Times New Roman"
        hs.font.color.rgb = {1: NAVY, 2: NAVY, 3: BLUE}[lvl]
        hs.font.size = Pt({1: 14, 2: 12, 3: 11}[lvl])
        hs.font.bold = True
    # accent rule under every level-1 heading
    h1 = doc.styles["Heading 1"]
    pPr = h1.element.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bot = OxmlElement("w:bottom")
    bot.set(qn("w:val"), "single")
    bot.set(qn("w:sz"), "12")
    bot.set(qn("w:color"), BLUE_FILL)
    pBdr.append(bot)
    pPr.append(pBdr)

    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)  # A4
    sec.top_margin = sec.bottom_margin = Cm(2.2)
    sec.left_margin = sec.right_margin = Cm(2.2)

    # ---------------- COVER (full-bleed, no header/footer) ----------------
    sec.top_margin = sec.bottom_margin = Cm(0)
    sec.left_margin = sec.right_margin = Cm(0)

    def _pad(cell, top=0, bottom=0, left=0, right=0):
        tcPr = cell._tc.get_or_add_tcPr()
        mar = OxmlElement("w:tcMar")
        for tag, val in (("top", top), ("bottom", bottom),
                         ("left", left), ("right", right)):
            e = OxmlElement(f"w:{tag}")
            e.set(qn("w:w"), str(int(val * 567)))
            e.set(qn("w:type"), "dxa")
            mar.append(e)
        tcPr.append(mar)

    def _fill(cell, colour):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:fill"), colour)
        tcPr.append(shd)

    def _full_width(t, cols=1):
        tblPr = t._tbl.tblPr
        w = tblPr.find(qn("w:tblW"))
        if w is None:
            w = OxmlElement("w:tblW")
            tblPr.append(w)
        w.set(qn("w:w"), "5000")
        w.set(qn("w:type"), "pct")
        ind = OxmlElement("w:tblInd")
        ind.set(qn("w:w"), "0")
        ind.set(qn("w:type"), "dxa")
        tblPr.append(ind)
        cm = OxmlElement("w:tblCellMar")
        for tag in ("top", "left", "bottom", "right"):
            e = OxmlElement(f"w:{tag}")
            e.set(qn("w:w"), "0")
            e.set(qn("w:type"), "dxa")
            cm.append(e)
        tblPr.append(cm)
        lay = OxmlElement("w:tblLayout")
        lay.set(qn("w:type"), "fixed")
        tblPr.append(lay)
        grid = t._tbl.find(qn("w:tblGrid"))
        if grid is not None:
            each = int(21.2 * 567 / cols)
            for gc in grid.findall(qn("w:gridCol")):
                gc.set(qn("w:w"), str(each))
        return t

    def _txt(cell, text, size, bold=False, colour=None, align="left",
             before=0, after=0, italic=False, first=False):
        p = cell.paragraphs[0] if (first and not cell.paragraphs[0].text) \
            else cell.add_paragraph()
        p.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT,
                       "center": WD_ALIGN_PARAGRAPH.CENTER,
                       "right": WD_ALIGN_PARAGRAPH.RIGHT}[align]
        p.paragraph_format.space_before = Pt(before)
        p.paragraph_format.space_after = Pt(after)
        r = p.add_run(text)
        r.bold = bold
        r.italic = italic
        r.font.size = Pt(size)
        if colour is not None:
            r.font.color.rgb = colour
        return p

    # 1 — white masthead: logo, tagline rule, national emblem
    head = doc.add_table(rows=1, cols=3)
    _full_width(head, 3)
    hl, hm, hr = head.rows[0].cells
    hl.width, hm.width, hr.width = Cm(7.0), Cm(8.6), Cm(5.4)
    _pad(hl, 0.75, 0.45, 1.5, 0.2)
    _pad(hm, 0.95, 0.45, 0.4, 0.2)
    _pad(hr, 0.75, 0.45, 0.2, 1.5)
    try:
        hl.paragraphs[0].add_run().add_picture(
            os.path.join(ASSETS, "logo_left.png"), height=Cm(1.35))
    except Exception:
        pass
    _txt(hm, "Science for a", 11, italic=True, colour=NAVY, first=True)
    _txt(hm, "Cleaner Tomorrow", 11, italic=True, colour=NAVY)
    rp = hr.paragraphs[0]
    rp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    try:
        rp.add_run().add_picture(
            os.path.join(ASSETS, "logo_right.png"), height=Cm(1.35))
    except Exception:
        pass

    # 2 — hero band (rendered per report: imagery + title + tagline)
    hero_t = doc.add_table(rows=1, cols=1)
    _full_width(hero_t)
    hero_c = hero_t.rows[0].cells[0]
    hp = hero_c.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    hp.paragraph_format.space_after = Pt(0)
    hp.add_run("{{ cover_hero }}")

    # 3 — value propositions
    vals = doc.add_table(rows=2, cols=4)
    _full_width(vals, 4)
    props = [
        ("accurate", "ACCURATE", "Precision monitoring\nwith calibrated instruments"),
        ("reliable", "RELIABLE", "Data you can trust,\nanytime, anywhere"),
        ("compliant", "COMPLIANT", "Aligned with KSA NCEC\n& international standards"),
        ("sustainable", "SUSTAINABLE", "Supporting a cleaner\nand healthier future"),
    ]
    for i, (icon, title, blurb) in enumerate(props):
        top = vals.cell(0, i)
        bot = vals.cell(1, i)
        top.width = bot.width = Cm(5.3)
        _pad(top, 0.45, 0.12, 0.3, 0.3)
        _pad(bot, 0.0, 0.45, 0.3, 0.3)
        ip = top.paragraphs[0]
        ip.alignment = WD_ALIGN_PARAGRAPH.CENTER
        ip.paragraph_format.space_after = Pt(3)
        try:
            ip.add_run().add_picture(
                os.path.join(ASSETS, f"icon_{icon}.png"), height=Cm(1.05))
        except Exception:
            pass
        _txt(bot, title, 9.5, bold=True, colour=GREEN_ACCENT, align="center",
             after=2, first=True)
        for line in blurb.split("\n"):
            _txt(bot, line, 8, colour=DARK, align="center", after=0)

    # 4 — project details card
    card = doc.add_table(rows=5, cols=2)
    _full_width(card, 2)
    card.style = "Table Grid"
    rows_ = [("CLIENT", "{{ client }}"),
             ("SITE", "{{ site_name }}"),
             ("MONITORING PERIOD", "{{ monitoring_window_text }}"),
             ("REPORT NUMBER", "{{ report_number }}"),
             ("REVISION / DATE", "{{ revision }}   |   {{ reporting_date }}")]
    for i, (k, v) in enumerate(rows_):
        kc, vc = card.cell(i, 0), card.cell(i, 1)
        kc.width, vc.width = Cm(6.0), Cm(15.2)
        _pad(kc, 0.17, 0.17, 1.5, 0.2)
        _pad(vc, 0.17, 0.17, 0.45, 0.4)
        _fill(kc, NAVY_FILL)
        _txt(kc, k, 9.5, bold=True, colour=WHITE, first=True)
        _txt(vc, v, 10, colour=DARK, first=True)

    # 5 — prepared by
    prep = doc.add_table(rows=1, cols=1)
    _full_width(prep)
    pc = prep.rows[0].cells[0]
    _pad(pc, 0.7, 0.6, 1.5, 1.5)
    _txt(pc, "PREPARED BY", 9.5, bold=True, colour=GREEN_ACCENT, first=True)
    _txt(pc, "{{ provider }}", 16, bold=True, colour=NAVY, before=2, after=1)
    _txt(pc, "Environmental Consultant", 10, colour=GREEN_ACCENT, after=6)
    _txt(pc, "Accredited by the National Center for Environmental "
             "Compliance (NCEC)", 8.5, italic=True, colour=MUTED_GREY, after=1)
    _txt(pc, "Reported to KSA NCEC 2020 ambient air quality standards", 8.5,
         italic=True, colour=MUTED_GREY)

    # 6 — navy contact footer
    foot_t = doc.add_table(rows=1, cols=1)
    _full_width(foot_t)
    fc = foot_t.rows[0].cells[0]
    _fill(fc, NAVY_FILL)
    _pad(fc, 0.5, 0.5, 1.5, 1.5)
    _txt(fc, "{{ provider_legal_name }}", 10.5, bold=True, colour=WHITE,
         first=True)
    _txt(fc, "Tel. {{ provider_tel }}    |    Fax {{ provider_fax }}    |    "
             "{{ provider_email }}    |    {{ provider_address }}", 8.5,
         colour=RGBColor(0xC5, 0xDA, 0xEC), before=3)

    sec2 = doc.add_section(WD_SECTION.NEW_PAGE)
    sec2.page_width, sec2.page_height = Cm(21.0), Cm(29.7)
    sec2.top_margin = sec2.bottom_margin = Cm(2.2)
    sec2.left_margin = sec2.right_margin = Cm(2.2)
    sec2.top_margin = Cm(3.2)
    _header_footer(sec2)

    # --- Document control page
    _p(doc, "Air quality Monitoring Report", size=16, bold=True, align="center",
       space_after=2)
    _p(doc, "for", size=12, align="center", space_after=2)
    _p(doc, "{{ project_name }}", size=15, bold=True, align="center", space_after=10)
    _p(doc, "Prepared by", size=12, align="center", space_after=2)
    _p(doc, "{{ provider }}", size=13, bold=True, align="center", space_after=14)

    meta = doc.add_table(rows=4, cols=2)
    meta.style = "Table Grid"
    for i, (k, v) in enumerate([
        ("Project", "{{ project_name }}"),
        ("Document Title", "Ambient Air Quality Monitoring Report"),
        ("Client", "{{ client }}"),
        ("Report Number", "{{ report_number }}"),
    ]):
        _cell_text(meta.cell(i, 0), k, bold=True, size=10)
        _shade(meta.cell(i, 0))
        _cell_text(meta.cell(i, 1), v, size=10)
    _p(doc, space_after=8)
    rev = doc.add_table(rows=2, cols=4)
    rev.style = "Table Grid"
    for j, h in enumerate(["Rev", "Reporting Date", "Prepared by", "Project supervision"]):
        _cell_text(rev.cell(0, j), h, bold=True, size=10, align="center")
        _shade(rev.cell(0, j))
    for j, v in enumerate(["{{ revision }}", "{{ reporting_date }}",
                           "{{ prepared_by }}", "{{ project_supervision }}"]):
        _cell_text(rev.cell(1, j), v, size=10, align="center")
    doc.add_page_break()

    # --- TOC / LoF / LoT
    _p(doc, "Table of Contents", size=14, bold=True, space_after=8)
    toc_p = doc.add_paragraph()
    _field(toc_p, ' TOC \\o "1-3" \\h \\z \\u ')
    doc.add_page_break()
    _p(doc, "List of Figures", size=14, bold=True, space_after=8)
    lof_p = doc.add_paragraph()
    _field(lof_p, ' TOC \\h \\z \\c "Figure" ')
    _p(doc, "List of Tables", size=14, bold=True, space_after=8)
    lot_p = doc.add_paragraph()
    _field(lot_p, ' TOC \\h \\z \\c "Table" ')
    doc.add_page_break()

    # --- Definitions & Abbreviations
    _p(doc, "Definitions & Abbreviations", size=14, bold=True, space_after=8)
    defs = [
        ("°C", "Degrees Celsius"),
        ("µg/m³", "Micrograms per cubic meter at standard temperature and pressure "
                  "(25°C and 101.3 kPa)"),
        ("W/m²", "Watt per square meter"),
        ("AAQMS", "Ambient Air Quality Monitoring Station"),
        ("CO", "Carbon Monoxide"),
        ("Deg.", "Degrees (True North)"),
        ("H₂S", "Hydrogen sulfide"),
        ("m/s", "Meters per second"),
        ("NO", "Nitric oxide"),
        ("NO2", "Nitrogen dioxide"),
        ("NOx", "Oxides of Nitrogen"),
        ("O3", "Ozone"),
        ("hPa", "Hecto Pascal"),
        ("PM10", "Particulate less than 10 microns in equivalent aerodynamic diameter"),
        ("PM2.5", "Particulate less than 2.5 microns in equivalent aerodynamic diameter"),
        ("ppb", "Parts per billion"),
        ("ppm", "Parts per million"),
        ("RH", "Relative Humidity"),
        ("SO₂", "Sulfur dioxide"),
        ("WD", "Wind Direction"),
        ("WS", "Wind Speed"),
    ]
    dt = doc.add_table(rows=len(defs), cols=2)
    for i, (a, b) in enumerate(defs):
        _cell_text(dt.cell(i, 0), a, bold=True, size=10)
        _cell_text(dt.cell(i, 1), b, size=10)
    doc.add_page_break()

    # --- Executive Summary
    _heading(doc, "Executive Summary", 1)
    _p(doc, "{{ provider }} was commissioned by {{ client }} to conduct ambient air "
            "quality monitoring at {{ project_name }}. Continuous ambient air "
            "monitoring was conducted at one location for a period of "
            "{{ monitoring_period_text }} by the air quality monitoring station "
            "(AQMS). The Air Quality Monitoring started on {{ monitoring_start_date }}. "
            "This report presents a summary of the validated data that was obtained "
            "for the period of {{ monitoring_window_text }}. The ambient air quality "
            "monitoring station (AAQMS) was equipped to measure standard air "
            "pollutants and meteorological parameters as listed below.",
       align="justify")
    lst = doc.add_table(rows=8, cols=2)
    heads = ["Air Pollutants Monitored", "Meteorological Parameters Monitored"]
    for j, h in enumerate(heads):
        _cell_text(lst.cell(0, j), h, bold=True, size=10)
        _shade(lst.cell(0, j))
    pol_names = ["Oxides of Nitrogen (NO2)", "Sulphur Dioxide (SO₂)",
                 "Carbon Monoxide (CO)", "Ozone (O3)", "Hydrogen Sulfide (H₂S)",
                 "Particulates Matter - PM10", "Particulates Matter - PM2.5"]
    met_names = ["Wind Speed", "Wind Direction", "Air Temperature",
                 "Relative Humidity", "Barometric Pressure", "", ""]
    for i in range(7):
        _cell_text(lst.cell(i + 1, 0), pol_names[i], size=10)
        _cell_text(lst.cell(i + 1, 1), met_names[i], size=10)
    _p(doc)
    _p(doc, "{{ capture_sentence }} For QA/QC checks, in accordance with the relevant "
            "United States Environmental Protection Agency (EPA) methods for each "
            "parameter, were carried out within the required schedule. USEPA data "
            "handling guidelines were followed in collecting, verifying, and "
            "validating continuous ambient air quality and meteorological monitoring "
            "data in this report.", align="justify")
    _caption(doc, "Table", "Percent of Data Captured for all Parameters.")
    cap = doc.add_table(rows=4, cols=5)
    cap.style = "Table Grid"
    for j, h in enumerate(["Parameters", "Total hours in monitoring period",
                           "Total available hours in monitoring period",
                           "Exception hours", "AAQMS 1-Hour's data capture %"]):
        _cell_text(cap.cell(0, j), h, bold=True, size=9, align="center")
        _shade(cap.cell(0, j))
    _tr_tag_row(cap, 1, "{%tr for r in capture_rows %}")
    row = cap.rows[2]
    _cell_text(row.cells[0], "{{ r.name }}", size=9)
    _cell_text(row.cells[1], "{{ r.total }}", size=9, align="center")
    _cell_text(row.cells[2], "{{ r.available }}", size=9, align="center")
    _cell_text(row.cells[3], "{{ r.exception }}", size=9, align="center")
    _cell_text(row.cells[4], "{{ r.capture }}", size=9, align="center")
    _tr_tag_row(cap, 3, "{%tr endfor %}")
    doc.add_page_break()

    # --- 1. Introduction
    _heading(doc, "1. Introduction", 1)
    _p(doc, "An ambient air quality monitoring survey was conducted for the "
            "{{ project_name }}. {{ provider }} ({{ provider_short }} - is an "
            "environmental laboratory in field of air quality monitoring approved by "
            "NCEC) installed the AQMS at one location in the proposed location as per "
            "client request and environmental judgment. {{ provider_short }} stations "
            "Lab was retained by {{ client }} and {{ provider_short }} was responsible "
            "for the operation and maintenance of the AAQMS as well as the validation "
            "of the data recorded. This report presents the data collected at the "
            "project site for the period of {{ monitoring_window_text }}.",
       align="justify")
    _p(doc, "This report summarizes the results obtained from the ambient air quality "
            "survey and field observations for any exceedances of the NCEC air "
            "quality standard. The ambient air quality standards used to identify "
            "pollution include the national standards set out in the Implementing "
            "Regulations for Air Quality of the Environmental Law issued by Royal "
            "Decree No. (M/165) as of 19/11/1441 AH. Graphical representations of "
            "the monitoring results within the context of the relevant limit values "
            "are also provided.", align="justify")
    _p(doc, "The following air pollutants were measured at each point:")
    for b in ["Particulate matter with aerodynamic diameters less than 10 microns (PM10),",
              "Particulate matter with aerodynamic diameters less than 2.5 microns (PM2.5),",
              "Sulfur dioxide (SO₂).", "Hydrogen Sulfide (H₂S).",
              "Oxides of Nitrogen (NO2).", "Ozone (O3).", "Carbon Monoxide (CO)."]:
        doc.add_paragraph(b, style="List Bullet")
    _p(doc, "In addition, meteorological data for wind speed, wind direction, ambient "
            "temperature, relative humidity, and barometric pressure were also "
            "measured.", align="justify")

    # --- 2. Monitoring and Data Collection
    _heading(doc, "2. Monitoring and Data Collection", 1)
    _heading(doc, "2.1 Site Details", 2)
    _p(doc, "The location of the ambient air quality monitoring station as shown in "
            "Table 2 and Figure 1. The Monitoring location was chosen by "
            "({{ client }}) and was intended to provide background or baseline data "
            "for the site. Inlet manifold length {{ inlet_height_m }} meters from "
            "ground level.", align="justify")
    _caption(doc, "Table", "Location of Ambient Air Quality Monitoring Stations")
    loc = doc.add_table(rows=2, cols=2)
    loc.style = "Table Grid"
    _cell_text(loc.cell(0, 0), "Site Name", bold=True, size=10, align="center")
    _shade(loc.cell(0, 0))
    _cell_text(loc.cell(0, 1), "Geographical Coordinates", bold=True, size=10,
               align="center")
    _shade(loc.cell(0, 1))
    _cell_text(loc.cell(1, 0), "{{ site_name }}", size=10, align="center")
    _cell_text(loc.cell(1, 1), "N {{ latitude }}   E {{ longitude }}", size=10,
               align="center")
    _p(doc, "{%p if fig_site_map %}", size=1, space_after=0)
    _p(doc, "{{ fig_site_map }}", align="center")
    _p(doc, "{%p endif %}", size=1, space_after=0)
    _caption(doc, "Figure", "Location of the Ambient Air quality monitor")
    grid = doc.add_table(rows=3, cols=2)
    grid.alignment = WD_TABLE_ALIGNMENT.CENTER
    _tr_tag_row(grid, 0, "{%tr for row in site_photo_rows %}")
    mid = grid.rows[1]
    for k, cell in enumerate(mid.cells):
        cp = cell.paragraphs[0]
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cp.add_run("{{ row[%d] }}" % k)
    _tr_tag_row(grid, 2, "{%tr endfor %}")
    _p(doc, "{%p if fig_site_photo %}", size=1, space_after=0)
    _p(doc, "{{ fig_site_photo }}", align="center")
    _p(doc, "{%p endif %}", size=1, space_after=0)
    _caption(doc, "Figure",
             "Location of the Ambient Air quality monitoring stations in the site")

    _heading(doc, "2.2 Monitoring Methodology", 2)
    _p(doc, "Monitoring methodology and Reference Measurement Principle and "
            "Calibration Procedures for the Measurement of Ambient Air Quality "
            "Pollutants are summarized in Table 3.", align="justify")
    _caption(doc, "Table", "Reference Measurement Principle and equivalent reference method")
    m = doc.add_table(rows=7, cols=5)
    m.style = "Table Grid"
    for j, h in enumerate(["Measured Parameter", "Data Collection Methods Used",
                           "Description of the Method", "Method Type",
                           "Automated Equivalent Reference Method ID"]):
        _cell_text(m.cell(0, j), h, bold=True, size=9, align="center")
        _shade(m.cell(0, j))
    method_rows = [
        ("Sulfur Dioxide (SO2)", "40 CFR Appendix A-1 to Part 50",
         "Reference Measurement Principle and Calibration Procedure for the "
         "Measurement of Sulfur Dioxide in the Atmosphere (Ultraviolet Fluorescence "
         "Method)", "FRM", "EQSA-0486-060"),
        ("Nitrogen Oxides (NO - NO2 - NOx)",
         "Code of Federal Regulations, Title 40, Part 50, Appendix F",
         "Measurement Principle and Calibration Procedure for the Measurement of "
         "Nitrogen Dioxide in the Atmosphere (Gas Phase Chemiluminescence)",
         "FRM", "RFNA-1289-074"),
        ("Ozone (O3)", "USEPA Code of Federal Regulations (Title 40, Part 50, "
         "Appendix D)", "Reference Measurement Principle and Calibration Procedure "
         "for the Measurement of Ozone in the Atmosphere (UV light absorption "
         "Method)", "FRM", "EQOA-0880-047"),
        ("Carbon Monoxide (CO)", "40 CFR Appendix C to Part 50",
         "Measurement Principle and Calibration Procedure for the Measurement of "
         "Carbon Monoxide in the Atmosphere (Non-Dispersive Infrared Photometry)",
         "FRM", "RFCA-0981-054"),
        ("Hydrogen Sulfide (H2S)", "Described below in detail", "NA", "NA", "NA"),
        ("Particulate Matter (PM10 & PM2.5)", "40 CFR 50 Appendix L",
         "Reference Method for the Determination of Fine Particulate Matter",
         "FRM", "EQPM-0609-183"),
    ]
    for i, r in enumerate(method_rows):
        for j, v in enumerate(r):
            _cell_text(m.cell(i + 1, j), v, size=8)
    _p(doc, "* FRM: Federal Reference Method", size=9, italic=True)

    _heading(doc, "2.3 Monitored Parameters", 2)
    _p(doc, "Table 4 below shows the details of parameters monitored and the "
            "instruments used at the monitoring station. Note that the "
            "meteorological instruments (wind Speed, wind direction, Temp, and RH) "
            "sensors installed at 10 m above ground level. Barometric pressure "
            "installed at 3 m above ground level.", align="justify")
    _caption(doc, "Table", "Parameters Measured at Air Quality Monitoring Stations")
    inst = doc.add_table(rows=4, cols=3)
    inst.style = "Table Grid"
    for j, h in enumerate(["PARAMETERS MEASURED", "SN",
                           "INSTRUMENT AND MEASUREMENTS TECHNIQUES"]):
        _cell_text(inst.cell(0, j), h, bold=True, size=9, align="center")
        _shade(inst.cell(0, j))
    _tr_tag_row(inst, 1, "{%tr for i in instruments %}")
    row = inst.rows[2]
    _cell_text(row.cells[0], "{{ i.parameter }}", size=9)
    _cell_text(row.cells[1], "{{ i.sn }}", size=9, align="center")
    _cell_text(row.cells[2], "{{ i.technique }}", size=9)
    _tr_tag_row(inst, 3, "{%tr endfor %}")
    _p(doc, "SN: serial number", size=9, italic=True)

    _heading(doc, "2.4 Data Collection Methods", 2)
    _heading(doc, "2.4.1 Compliance with Standards", 3)
    _p(doc, "The instruments used in the stations were approved by the US EPA and "
            "all procedures for ambient air monitoring are in accordance with US "
            "EPA procedures.", align="justify")
    _heading(doc, "2.4.2 Data Acquisition", 3)
    _p(doc, "Data acquisition was performed by using a PC based situated at each of "
            "the monitoring sites. Data was logged every 15 seconds and stored every "
            "1 minute. The data was backed up and downloaded every day and subjected "
            "to a rigorous program of quality checking.", align="justify")

    _heading(doc, "2.5 Data Validation and Reporting", 2)
    _heading(doc, "2.5.1 Validation", 3)
    _p(doc, "The purpose of the data validation section is to specify the guidelines "
            "that have been taken into consideration whenever possible in "
            "collecting, verifying, and validating continuous ambient air quality "
            "and meteorological monitoring data in this project.", align="justify")
    _p(doc, "{{ provider_short }} maintains one distinct database containing "
            "non-validated and validated data respectively. The validated database "
            "is created by duplicating the non-validated database and then flagging "
            "data affected by instrument faults, calibrations, and other maintenance "
            "activities. Invalid data is removed with the support of valid reason "
            "e.g., supported by maintenance notes, calibration sheets etc. as "
            "documented in exception tables.", align="justify")
    _p(doc, "Validation is performed by a trained data analyst. All data is checked "
            "and reviewed by the {{ provider_short }} section head. Graphs and "
            "reports are generated based on the validated hourly data and daily "
            "data.", align="justify")
    _heading(doc, "2.5.2 Data Validation Levels", 3)
    for lead, body in [
        ("Level 0", "Routine checks – Field and laboratory operations, data "
         "processing, reporting conducted in accordance with Standard Operating "
         "Procedures (SOPs) – Proper data file identification; review of unusual "
         "events, field data sheets, and result reports; instrument performance "
         "checks."),
        ("Level I", "Internal consistency tests – Identify values that appear "
         "atypical when compared to the values of the entire dataset."),
        ("Level II/III", "External consistency tests – Identify values in the data "
         "that appear atypical when compared to other datasets – Continued "
         "evaluation of the data as part of the data interpretation process."),
    ]:
        p = _p(doc, "", align="justify")
        r = p.add_run(lead)
        r.bold = True
        p.add_run(" — " + body)
    _p(doc, "Outliers are values that lie outside most of the other values in a set "
            "of data. Outliers treated as valid/suspect until proven invalid. The "
            "first assumption upon finding a measurement that is inconsistent with "
            "physical expectations is that the unusual value is due to a measurement "
            "error. If upon tracing the path of the measurement, nothing unusual is "
            "found, the value can be assumed to be a valid result of an "
            "environmental cause.", align="justify")
    _heading(doc, "2.5.3 Considerations in Evaluating AAQ Data", 3)
    for b in ["Levels of other pollutants", "Time of day/year",
              "Observations at other sites", "Audits and inter-laboratory comparisons",
              "Instrument performance history", "Calibration drift",
              "Site characteristics", "Meteorology", "Exceptional events"]:
        doc.add_paragraph(b, style="List Bullet")
    _p(doc, "Visual Data Review: Time Series are visually inspected for the below:")
    for b in ["Jumps, dips.", "Periodicity of peaks", "Calibration gas, carryover",
              "Expected diurnal pattern.", "Expected relationships.",
              "High concentrations of less abundant species or low concentrations "
              "of more abundant species"]:
        doc.add_paragraph(b, style="List Bullet")
    _p(doc, "Data is put into perspective of:")
    for b in ["Local, regional, or national averages", "Trends over time",
              "Comparison to nearby sites, similar areas", "Detection limits"]:
        doc.add_paragraph(b, style="List Bullet")
    _heading(doc, "2.5.4 Reporting", 3)
    _p(doc, "The reported data is provided in a Microsoft Excel spreadsheet. The "
            "data contained in these reports is based on Kingdom of Saudi Arabia "
            "(KSA) time.", align="justify")

    # --- 3. Standards
    _heading(doc, "3. Ambient Air Quality Standards", 1)
    _p(doc, "The air quality monitoring station's data has been compared to the "
            "NCEC's 2020 ambient air quality standards. Table 5 summarizes the "
            "NCEC's 2020 ambient air quality standards for the pollutants studied. "
            "Note that CO and O3 averages are rolling averages whereas all other "
            "averages are fixed averages.", align="justify")
    _caption(doc, "Table", "KSA NCEC Ambient Air Quality Standards")
    ncec = doc.add_table(rows=4, cols=5)
    ncec.style = "Table Grid"
    for j, h in enumerate(["Parameter", "Time Period", "Exceedance Level", "Units",
                           "Number of Allowable Exceedances"]):
        _cell_text(ncec.cell(0, j), h, bold=True, size=9, align="center")
        _shade(ncec.cell(0, j))
    _tr_tag_row(ncec, 1, "{%tr for l in ncec_rows %}")
    row = ncec.rows[2]
    _cell_text(row.cells[0], "{{ l.pollutant }}", size=9, align="center")
    _cell_text(row.cells[1], "{{ l.period }}", size=9, align="center")
    _cell_text(row.cells[2], "{{ l.limit }}", size=9, align="center")
    _cell_text(row.cells[3], "µg/m³", size=9, align="center")
    _cell_text(row.cells[4], "{{ l.allowance }}", size=9, align="center")
    _tr_tag_row(ncec, 3, "{%tr endfor %}")

    # --- 4. Calibrations and Maintenance
    _heading(doc, "4. Calibrations and Maintenance", 1)
    _heading(doc, "4.1 Maintenance", 2)
    _p(doc, "Regular maintenance was carried out by {{ provider_short }}. Sample "
            "inlets of all analyzers were cleaned before installation and on a "
            "weekly basis. Filters of gas analyzers were changed before the start "
            "of monitoring. Meteorological sensors cleaned before installation. In "
            "addition, the regular maintenance program conducted as per standard or "
            "operation manual such as: meteorological sensors should be cleaned "
            "after rain because the dust particles stick to the meteorological "
            "sensors. After every sandstorm, inlets of all analyzers as well as "
            "manifolds of the gas analyzers should be cleaned to protect analyzers "
            "from particulate matter.", align="justify")
    _heading(doc, "4.2 Calibration", 2)
    _p(doc, "Multipoint calibration of the instruments monitoring gaseous pollutants "
            "was conducted one time before the monitoring period. The instruments "
            "were calibrated in full accordance with the manufacturer's "
            "recommendations and conform to the requirements of USEPA. Calibrations "
            "were performed at the monitoring site by allowing the analyzer to "
            "sample a gaseous standard containing a known pollutant concentration. "
            "Calibration data were recorded by the same data acquisitions system. "
            "Mast wind direction system was oriented at South direction as per "
            "manufacture operation manual.", align="justify")

    # --- 5. Results and discussion
    _heading(doc, "5. Results and discussion", 1)
    _heading(doc, "5.1 Air Quality Summary", 2)
    _p(doc, "Tables 6 to 13 compare monitoring results for AAQMS for the period of "
            "{{ monitoring_window_text }} on the site. The results are explained as "
            "follows:", align="justify")
    _p(doc, "- Air Pollutants Monitored results", bold=True)

    # 5.1.1 SO2
    _heading(doc, "5.1.1 Sulphur Dioxide (SO2)", 3)
    _p(doc, "Levels of Sulphur dioxide (SO2) in ambient air are typically directly "
            "related to the concentration of Sulphur in fuel and the quantity of "
            "fuel being combusted. Upon combustion, approximately 98% of the "
            "Sulphur in the fuel will oxidize to form SO2, with the remaining 2% "
            "producing Sulphur trioxide (SO3). The emitted SO2 can also further "
            "oxidize to SO3 and react with water to produce acid rain in the form "
            "of sulphury acid (H2SO4). Short-term exposures to SO2 have shown "
            "adverse respiratory effects including bronchoconstriction and "
            "increased asthma symptoms.", align="justify")
    _p(doc, "{{ so2.narrative }}", align="justify")
    _caption(doc, "Table", "Summary of SO₂ Results")
    _summary_table(doc, [
        ("Percentage data capture (Hourly Values)", "{{ so2.capture }}"),
        ("Hourly Maximum (ug/m³)", "{{ so2.h_max }}"),
        ("Hourly Minimum (ug/m³)", "{{ so2.h_min }}"),
        ("Daily average (ug/m³)", "{{ so2.daily_avg }}"),
        ("Hourly value > {{ so2.limit_1h }} (ug/m³)", "{{ so2.exceed_1h }}"),
    ], [("1 Hour", "{{ so2.limit_1h }}"), ("24 Hour", "{{ so2.limit_24h }}")])
    _p(doc, "{{ so2.footnote }}", size=9, italic=True)
    _p(doc, "{{ fig_so2 }}", align="center")
    _caption(doc, "Figure", "SO2 Hourly Concentration at the location.")

    # 5.1.2 NO/NO2/NOx
    _heading(doc, "5.1.2 Oxides of Nitrogen (NO, NO2, NOx)", 3)
    _p(doc, "In a combustion process, NOx is produced through three mechanisms, "
            "namely thermal NOx, fuel NOx and prompt NOx. Thermal NOx is the primary "
            "source of NOx and is formed as a high temperature dissociation and "
            "subsequent reaction of nitrogen (N2) and oxygen (O2). NO2 is the "
            "primary component of concern in NOx emissions. Generally, up to 10% of "
            "the NOx emitted from the combustion of fuel is emitted as NO2. The "
            "remainder is emitted as NO, which is subsequently converted to NO2 in "
            "reactions with various oxidants and ozone as the plume is transported "
            "downwind from the source. NO2 is a reddish-brown gas with a pungent "
            "odor, which upon reaction with other atmospheric compounds, becomes a "
            "major contributor to smog, acid rain, inhalable particulates and "
            "reduced visibility. At significant levels and exposure, inhalation may "
            "result in irritation and burning to the skin and eyes, nose, and "
            "throat. Prolonged exposure may result in permanent lung damage.",
       align="justify")
    _p(doc, "{{ nox_group.narrative }}", align="justify")
    _caption(doc, "Table", "Summary of (NO, NO2, NOx) Results.")
    nx = doc.add_table(rows=16, cols=3)
    nx.style = "Table Grid"
    hdr = _merge_row(nx, 0, 0, 1)
    _cell_text(hdr, "NO₂ Concentration at sampling point", bold=True, size=10)
    _shade(hdr)
    _cell_text(nx.cell(0, 2), "NCEC Exceedance Level µg/m³ — 1 Hour", bold=True,
               size=9, align="center")
    _shade(nx.cell(0, 2))
    no2_rows = [
        ("Percentage data capture (Hourly Values)", "{{ no2.capture }}"),
        ("Hourly Maximum (ug/m³)", "{{ no2.h_max }}"),
        ("Hourly Minimum (ug/m³)", "{{ no2.h_min }}"),
        ("Hourly value > {{ no2.limit_1h }} (ug/m³)", "{{ no2.exceed_1h }}"),
        ("Daily average (ug/m³)", "{{ no2.daily_avg }}"),
    ]
    for i, (a, b) in enumerate(no2_rows):
        _cell_text(nx.cell(1 + i, 0), a, size=10)
        _cell_text(nx.cell(1 + i, 1), b, size=10, align="center")
    lim_cell = nx.cell(1, 2).merge(nx.cell(5, 2))
    _cell_text(lim_cell, "{{ no2.limit_1h }}", size=10, align="center")
    hdr2 = _merge_row(nx, 6, 0, 1)
    _cell_text(hdr2, "NO", bold=True, size=10)
    _shade(hdr2)
    _cell_text(nx.cell(6, 2), "NA", size=10, align="center")
    no_rows = [
        ("Percentage data capture (Hourly Values)", "{{ no.capture }}"),
        ("Hourly Maximum (ug/m³)", "{{ no.h_max }}"),
        ("Hourly Minimum (ug/m³)", "{{ no.h_min }}"),
        ("Daily average (ug/m³)", "{{ no.daily_avg }}"),
    ]
    for i, (a, b) in enumerate(no_rows):
        _cell_text(nx.cell(7 + i, 0), a, size=10)
        _cell_text(nx.cell(7 + i, 1), b, size=10, align="center")
    na1 = nx.cell(7, 2).merge(nx.cell(10, 2))
    _cell_text(na1, "NA", size=10, align="center")
    hdr3 = _merge_row(nx, 11, 0, 1)
    _cell_text(hdr3, "NOX", bold=True, size=10)
    _shade(hdr3)
    _cell_text(nx.cell(11, 2), "NA", size=10, align="center")
    nox_rows = [
        ("Percentage data capture (Hourly Values)", "{{ nox.capture }}"),
        ("Hourly Maximum (ug/m³)", "{{ nox.h_max }}"),
        ("Hourly Minimum (ug/m³)", "{{ nox.h_min }}"),
        ("Daily average (ug/m³)", "{{ nox.daily_avg }}"),
    ]
    for i, (a, b) in enumerate(nox_rows):
        _cell_text(nx.cell(12 + i, 0), a, size=10)
        _cell_text(nx.cell(12 + i, 1), b, size=10, align="center")
    na2 = nx.cell(12, 2).merge(nx.cell(15, 2))
    _cell_text(na2, "NA", size=10, align="center")
    _p(doc, "{{ nox_group.footnote }}", size=9, italic=True)
    _p(doc, "{{ fig_no }}", align="center")
    _caption(doc, "Figure", "NO Hourly Concentration at the location.")
    _p(doc, "{{ fig_no2 }}", align="center")
    _caption(doc, "Figure", "NO2 Hourly Concentration at the location.")
    _p(doc, "{{ fig_nox }}", align="center")
    _caption(doc, "Figure", "NOX Hourly Concentration at the location.")

    # 5.1.3 CO
    _heading(doc, "5.1.3 Carbon Monoxide (CO)", 3)
    _p(doc, "Carbon monoxide is a colorless and odorless gas which reduces the "
            "delivery of oxygen to the body's organs. For those with heart disease, "
            "exposure to low doses can result in chest pain. For healthier people, "
            "exposure to higher levels affects the central nervous system. "
            "Incomplete oxidation of fuel results in the formation of CO.",
       align="justify")
    _p(doc, "{{ co.narrative }}", align="justify")
    _caption(doc, "Table", "Summary of CO Results.")
    _summary_table(doc, [
        ("Percentage data capture (Hourly Values)", "{{ co.capture }}"),
        ("Hourly Maximum (ug/m³)", "{{ co.h_max }}"),
        ("Hourly Minimum (ug/m³)", "{{ co.h_min }}"),
        ("8 Hour Maximum (ug/m³)", "{{ co.r8_max }}"),
        ("8 Hour Minimum (ug/m³)", "{{ co.r8_min }}"),
        ("Hourly value > {{ co.limit_1h }} (ug/m³)", "{{ co.exceed_1h }}"),
        ("8-Hourly rolling average value > {{ co.limit_8h }} (ug/m³)",
         "{{ co.exceed_8h }}"),
        ("Daily average (ug/m³)", "{{ co.daily_avg }}"),
    ], [("1 Hour", "{{ co.limit_1h }}"), ("8 Hour", "{{ co.limit_8h }}")])
    _p(doc, "{{ co.footnote }}", size=9, italic=True)
    _p(doc, "{{ fig_co }}", align="center")
    _caption(doc, "Figure", "CO Hourly Concentration at the location.")
    _p(doc, "{{ fig_co8h }}", align="center")
    _caption(doc, "Figure", "CO 8 Hour Rolling Average Concentrations at the location.")

    # 5.1.4 H2S
    _heading(doc, "5.1.4 Hydrogen sulfide (H2S)", 3)
    _p(doc, "Hydrogen sulfide is a chemical compound with the formula H2S. It is a "
            "colorless chalcogen-hydride gas, and is poisonous, corrosive, and "
            "flammable, with trace amounts in ambient atmosphere having a "
            "characteristic foul odor of rotten eggs.", align="justify")
    _p(doc, "{{ h2s.narrative }}", align="justify")
    _caption(doc, "Table", "Summary of H₂S Results.")
    _summary_table(doc, [
        ("Percentage data capture (Hourly Values)", "{{ h2s.capture }}"),
        ("Hourly Maximum (µg/m³)", "{{ h2s.h_max }}"),
        ("Hourly Minimum (µg/m³)", "{{ h2s.h_min }}"),
        ("Hourly value > {{ h2s.limit_1h }} (ug/m³)", "{{ h2s.exceed_1h }}"),
        ("Daily Average (µg/m³)", "{{ h2s.daily_avg }}"),
    ], [("1 Hour", "{{ h2s.limit_1h }}"), ("24 Hour", "{{ h2s.limit_24h }}")])
    _p(doc, "{{ h2s.footnote }}", size=9, italic=True)
    _p(doc, "{{ fig_h2s }}", align="center")
    _caption(doc, "Figure", "H2S Hourly Concentration at the location.")

    # 5.1.5 O3
    _heading(doc, "5.1.5 Ozone (O3)", 3)
    _p(doc, "Ozone forms a protective layer which prevents entry of harmful "
            "ultraviolet radiation into the earth. The ground ozone is very harmful "
            "to human beings and the environment. It is released from industries, "
            "automobile emissions, gasoline vapors, solvents, chemicals, and "
            "electronic devices. Nitrogen oxides (NOx) and total Volatile Organic "
            "Compounds (TVOCs) also contribute to ground ozone formation. Ground "
            "ozone interferes with the plant's respiration process and enhances "
            "environmental stressor susceptibility. When ozone is inhaled by "
            "humans, reduced lung function, inflammation of airways, and irritation "
            "in the eyes, nose & throat are seen.", align="justify")
    _p(doc, "{{ o3.narrative }}", align="justify")
    _caption(doc, "Table", "Summary of O3 Result.")
    _summary_table(doc, [
        ("Percentage data capture (Hourly Values)", "{{ o3.capture }}"),
        ("Hourly Maximum (ug/m³)", "{{ o3.h_max }}"),
        ("8 Hour Maximum (ug/m³)", "{{ o3.r8_max }}"),
        ("8 Hour value > {{ o3.limit_8h }} (ug/m³)", "{{ o3.exceed_8h }}"),
        ("Daily average (ug/m³)", "{{ o3.daily_avg }}"),
    ], [("8 Hour", "{{ o3.limit_8h }}")])
    _p(doc, "{{ o3.footnote }}", size=9, italic=True)
    _p(doc, "{{ fig_o3 }}", align="center")
    _caption(doc, "Figure", "O3 Hourly Concentration at the location.")
    _p(doc, "{{ fig_o38h }}", align="center")
    _caption(doc, "Figure", "O3 8 Hour Rolling Average Concentrations at the location.")
    _p(doc, "{{ fig_no2_o3 }}", align="center")
    _caption(doc, "Figure", "NO2 vs. O3 Hourly Concentrations at the location.")

    # 5.1.6 PM
    _heading(doc, "5.1.6 Particulate Matter (PM10 & PM2.5)", 3)
    _p(doc, "A mixture of particles with liquid droplets in the air forms "
            "particulate matter. PM10 are particles that have a size of less than "
            "or equal to 10 microns whereas PM2.5 are ultra-fine particles having a "
            "size of less than or equal to 2.5 microns. Particulate Matter is "
            "released from constructions, smoking, cleanings, renovations, "
            "demolitions, natural hazards such as earthquakes, volcanic eruptions, "
            "and emissions from industries such as brick kilns, paper & pulp, etc. "
            "These particles, when inhaled, can penetrate deeper into the "
            "respiratory system, and cause respiratory ailments such as asthma, "
            "coughing, sneezing, irritation in the airways, eyes, nose, throat "
            "irritation, etc. Studies have also shown links between PM exposure and "
            "diabetes.", align="justify")
    _p(doc, "{{ pm_group.narrative }}", align="justify")
    _caption(doc, "Table", "Summary of PM10 Results.")
    _summary_table(doc, [
        ("Percentage data capture (Hourly Values)", "{{ pm10.capture }}"),
        ("Hourly Maximum (ug/m³)", "{{ pm10.h_max }}"),
        ("Hourly Minimum (ug/m³)", "{{ pm10.h_min }}"),
        ("Daily Values > {{ pm10.limit_24h }} (ug/m³)", "{{ pm10.exceed_24h }}"),
        ("Daily average (ug/m³)", "{{ pm10.daily_avg }}"),
    ], [("24 Hour", "{{ pm10.limit_24h }}")])
    _p(doc, "{{ pm10.footnote }}", size=9, italic=True)
    _caption(doc, "Table", "Summary of PM2.5 Results.")
    _summary_table(doc, [
        ("Percentage data capture (Hourly Values)", "{{ pm25.capture }}"),
        ("Hourly Maximum (ug/m³)", "{{ pm25.h_max }}"),
        ("Hourly Minimum (ug/m³)", "{{ pm25.h_min }}"),
        ("Daily Values > {{ pm25.limit_24h }} (ug/m³)", "{{ pm25.exceed_24h }}"),
        ("Daily average (ug/m³)", "{{ pm25.daily_avg }}"),
    ], [("24 Hour", "{{ pm25.limit_24h }}")])
    _p(doc, "{{ pm25.footnote }}", size=9, italic=True)
    _p(doc, "{{ fig_pm10 }}", align="center")
    _caption(doc, "Figure", "PM10 Hourly Concentrations at the location.")
    _p(doc, "{{ fig_pm25 }}", align="center")
    _caption(doc, "Figure", "PM2.5 Hourly Concentrations at the location.")

    # Meteorology
    _p(doc, "- Meteorological Parameters Monitored result:", bold=True)
    _p(doc, "The evaluation and interpretation of gas emission measurements is only "
            "possible in comparison with meteorological data acquired concurrently. "
            "The structure of the atmosphere close to the ground is extremely "
            "important for the local climate. Knowing solar radiation as well as "
            "the air humidity and air temperature is necessary to evaluate chemical "
            "reactions of pollutants in the air.", align="justify")
    _heading(doc, "5.1.7 Temperature and humidity", 3)
    _p(doc, "Temperature and humidity play a significant role in gas emission "
            "measurements. The recorded data of temperature and humidity was "
            "captured for {{ monitoring_hours }} hours. The results for the location "
            "were summarized in the following table, and represented on a graph "
            "(Figures below).", align="justify")
    _heading(doc, "5.1.8 Barometric pressure", 3)
    _p(doc, "To predict the weather, it must be the first understanding how "
            "atmospheric pressure works. The higher the barometric pressure, the "
            "better it is for good weather conditions. Conversely, low pressures "
            "generally bring in more clouds and moisture, leading to poor "
            "visibility and even precipitation or snowfall. The recorded data of "
            "Barometric pressure was captured for {{ monitoring_hours }} hours.",
       align="justify")
    _heading(doc, "5.1.9 Wind speed and direction", 3)
    _p(doc, "Wind speed describes how fast the air is moving past a certain point. "
            "Wind direction describes the direction on a compass from which the "
            "wind emanates. Wind speed and direction are important for monitoring "
            "and predicting weather patterns and global climate. The recorded data "
            "of Wind speed and direction was captured for {{ monitoring_hours }} "
            "hours at the location. The results were summarized in the following "
            "table, and represented on a graph. Also, the Wind speed and direction "
            "were represented as a wind rose, and the wind frequency count and "
            "distribution was mentioned in the tables below. A wind rose is a "
            "graphic tool used by meteorologists to give a succinct view of how "
            "wind speed and direction are typically distributed at a particular "
            "location. Using a polar coordinate system of gridding, the frequency "
            "of winds over a period is plotted by wind direction, with color bands "
            "showing wind speed ranges. The direction of the longest spoke shows "
            "the wind direction with the greatest frequency.", align="justify")
    _caption(doc, "Table", "Monitored Meteorological Parameters result.")
    met = doc.add_table(rows=17, cols=2)
    met.style = "Table Grid"
    met_rows = [
        ("Ambient Temperature result", None),
        ("Percentage data capture (Hourly Values)", "{{ met.temp_capture }}"),
        ("Hourly Maximum (⁰C)", "{{ met.temp_max }}"),
        ("Hourly Minimum (⁰C)", "{{ met.temp_min }}"),
        ("Relative Humidity result", None),
        ("Percentage data capture (Hourly Values)", "{{ met.rh_capture }}"),
        ("Hourly Maximum (%)", "{{ met.rh_max }}"),
        ("Hourly Minimum (%)", "{{ met.rh_min }}"),
        ("Barometric Pressure result", None),
        ("Percentage data capture (Hourly Values)", "{{ met.pressure_capture }}"),
        ("Hourly Max (hPa)", "{{ met.pressure_max }}"),
        ("Hourly Minimum (hPa)", "{{ met.pressure_min }}"),
        ("Wind Parameters result", None),
        ("Percentage data capture (Hourly Values)", "{{ met.ws_capture }}"),
        ("Wind Speed Hourly Maximum (m/s)", "{{ met.ws_max }}"),
        ("Wind Speed Hourly Minimum (m/s)", "{{ met.ws_min }}"),
        ("Mean Wind Speed (m/s) / Prevailing Wind Direction",
         "{{ met.ws_mean }} / {{ met.prevailing }}"),
    ]
    for i, (a, b) in enumerate(met_rows):
        if b is None:
            merged = _merge_row(met, i, 0, 1)
            _cell_text(merged, a, bold=True, size=10)
            _shade(merged)
        else:
            _cell_text(met.cell(i, 0), a, size=10)
            _cell_text(met.cell(i, 1), b, size=10, align="center")
    for key, cap_text in [
        ("fig_temp", "Hourly Temperature at the location."),
        ("fig_rh", "Hourly Relative Humidity at the location."),
        ("fig_pressure", "Hourly Pressure at the location."),
        ("fig_ws", "Hourly Wind Speed at the location."),
        ("fig_windrose", "Wind Rose at the location."),
        ("fig_windclassfreq", "Wind class frequency distribution graph at the location."),
    ]:
        _p(doc, "{{ %s }}" % key, align="center")
        _caption(doc, "Figure", cap_text)

    # Wind tables 14/15 — dynamic columns via dedicated {%tc %} cells
    for cap_text, rows_key, totals_key in [
        ("Wind class frequency distribution at the location.", "wind_pct_rows",
         "wind_pct_totals"),
        ("Wind class count at the location.", "wind_count_rows", "wind_count_totals"),
    ]:
        _caption(doc, "Table", cap_text)
        wt = doc.add_table(rows=7, cols=5)
        wt.style = "Table Grid"
        # header row: label | tc-for | {{c}} | tc-endfor | Total
        _cell_text(wt.cell(0, 0), "Directions / Wind Classes (m/s)", bold=True, size=9)
        _shade(wt.cell(0, 0))
        wt.cell(0, 1).paragraphs[0].text = "{%tc for c in wind_class_labels %}"
        _cell_text(wt.cell(0, 2), "{{ c }}", bold=True, size=9, align="center")
        _shade(wt.cell(0, 2))
        wt.cell(0, 3).paragraphs[0].text = "{%tc endfor %}"
        _cell_text(wt.cell(0, 4), "Total", bold=True, size=9, align="center")
        _shade(wt.cell(0, 4))
        # looped data rows
        _tr_tag_row(wt, 1, "{%%tr for r in %s %%}" % rows_key)
        _cell_text(wt.cell(2, 0), "{{ r.direction }}", size=9)
        wt.cell(2, 1).paragraphs[0].text = "{%tc for v in r.vals %}"
        _cell_text(wt.cell(2, 2), "{{ v }}", size=9, align="center")
        wt.cell(2, 3).paragraphs[0].text = "{%tc endfor %}"
        _cell_text(wt.cell(2, 4), "{{ r.total }}", size=9, align="center")
        _tr_tag_row(wt, 3, "{%tr endfor %}")
        # sub-total row
        _cell_text(wt.cell(4, 0), "Sub-Total", bold=True, size=9)
        wt.cell(4, 1).paragraphs[0].text = "{%%tc for v in %s %%}" % totals_key
        _cell_text(wt.cell(4, 2), "{{ v }}", size=9, align="center")
        wt.cell(4, 3).paragraphs[0].text = "{%tc endfor %}"
        _cell_text(wt.cell(4, 4), "{{ %s_grand }}" % totals_key, size=9,
                   align="center")
        # calms / missing rows (span value columns)
        _cell_text(wt.cell(5, 0), "Calms", size=9)
        c5 = wt.cell(5, 1).merge(wt.cell(5, 4))
        _cell_text(c5, "{{ %s_calms }}" % totals_key, size=9, align="center")
        _cell_text(wt.cell(6, 0), "Missing/Incomplete", size=9)
        c6 = wt.cell(6, 1).merge(wt.cell(6, 4))
        _cell_text(c6, "{{ %s_missing }}" % totals_key, size=9, align="center")
        _p(doc, space_after=6)

    # --- 6. Conclusions
    _heading(doc, "6. Conclusions", 1)
    _p(doc, "Key observations arising from the examination of the recorded data for "
            "the monitoring period in the project site "
            "({{ monitoring_window_text }}).", align="justify")
    doc.add_paragraph("The average data capture for the station was "
                      "{{ overall_capture }} % for air quality and meteorological "
                      "parameters.", style="List Bullet")
    p = doc.add_paragraph(style="Normal")
    p.add_run("{%p for c in conclusion_blocks %}")
    doc.add_paragraph("For {{ c.title }} concentrations:", style="List Bullet")
    p2 = doc.add_paragraph(style="Normal")
    p2.add_run("{%p for line in c.lines %}")
    doc.add_paragraph("- {{ line }}", style="List Bullet 2")
    p3 = doc.add_paragraph(style="Normal")
    p3.add_run("{%p endfor %}")
    p4 = doc.add_paragraph(style="Normal")
    p4.add_run("{%p endfor %}")
    doc.add_paragraph("{{ met_conclusion_1 }}", style="List Bullet")
    doc.add_paragraph("{{ met_conclusion_2 }}", style="List Bullet")
    doc.add_paragraph("{{ met_conclusion_3 }}", style="List Bullet")
    doc.add_paragraph("{{ met_conclusion_4 }}", style="List Bullet")
    _p(doc, "The prevailing wind direction at the site was {{ met.prevailing }}.")

    # --- Appendices
    doc.add_page_break()
    _heading(doc, "Appendix 1 Valid Data Exception", 1)
    _p(doc, "{{ appendix1_text }}", align="justify")
    _heading(doc, "Appendix 2 Valid Data Terms", 1)
    for lead, body in [
        ("Span / zero check.", " A manual zero calibration check is performed "
         "whereby air is passed through filter element, removing particulates, "
         "before entering the sensor in the analyzer. Data is invalidated when "
         "these checks occur."),
        ("Multipoint Calibration.", " To perform multipoint calibration, span and "
         "zero gases are passed through filter element, removing particulates, "
         "before entering the sensor in the analyzer. Data is invalidated when "
         "calibration occurs."),
        ("Instrument fault", " refers to a period when the instrument was not in "
         "the normal operating mode and did not measure a representative value of "
         "the existing conditions."),
        ("Data Communication Issue", " refers to a period when instrument is not "
         "connected to data logger (Configuration lost)."),
        ("Power Interruption", " refers to no power to the AAQMS therefore no data "
         "was collected at that time."),
    ]:
        pp = _p(doc, "", align="justify")
        rr = pp.add_run(lead)
        rr.bold = True
        pp.add_run(body)
    _heading(doc, "Appendix 3 Calibration certificates", 1)
    _p(doc, "{%p if calibration_images %}", size=1, space_after=0)
    _p(doc, "{%p for c in calibration_images %}", size=1, space_after=0)
    _p(doc, "{{ c.title }}", bold=True, size=10, color=NAVY, space_after=4)
    _p(doc, "{{ c.image }}", align="center")
    _p(doc, "{%p endfor %}", size=1, space_after=0)
    _p(doc, "{%p else %}", size=1, space_after=0)
    _p(doc, "[Calibration certificates to be attached — upload scanned "
            "certificates for this campaign.]", italic=True)
    _p(doc, "{%p endif %}", size=1, space_after=0)
    _heading(doc, "Appendix 4 Environmental license for the institution", 1)
    _p(doc, "{%p if license_images %}", size=1, space_after=0)
    _p(doc, "{%p for img in license_images %}", size=1, space_after=0)
    _p(doc, "{{ img }}", align="center")
    _p(doc, "{%p endfor %}", size=1, space_after=0)
    _p(doc, "{%p else %}", size=1, space_after=0)
    _p(doc, "[Environmental license to be attached — upload scanned license for "
            "this provider.]", italic=True)
    _p(doc, "{%p endif %}", size=1, space_after=0)

    _update_fields_on_open(doc)
    _modernise_settings(doc)
    doc.save(out_path)
    return out_path


if __name__ == "__main__":
    path = build()
    print(f"Template written: {path}")
