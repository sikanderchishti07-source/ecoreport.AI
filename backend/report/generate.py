"""Phase 3 orchestrator — render the full AAQ report DOCX for a campaign.

Pipeline: readings + limits -> CampaignSummary (calc.py) -> charts (charts.py)
-> context (context.py) -> docxtpl render of master_template.docx.
Charts are regenerated from the raw data on every call.
"""
from __future__ import annotations

import os
import sys
import tempfile
from typing import Dict, List, Optional, Tuple

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

from calc import build_campaign_summary, _as_utc
from models import Campaign, PollutantLimit, Reading
from report.charts import generate_all_charts
from report.context import build_context

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "master_template.docx")
TEMPLATE_PATH_AR = os.path.join(os.path.dirname(__file__),
                                "master_template_ar.docx")

FIG_WIDTH_MM = 155
ROSE_WIDTH_MM = 130

# figure context key -> chart key produced by generate_all_charts
FIG_MAP = {
    "fig_so2": "so2_hourly",
    "fig_no": "no_hourly",
    "fig_no2": "no2_hourly",
    "fig_nox": "nox_hourly",
    "fig_co": "co_hourly",
    "fig_co8h": "co_8h",
    "fig_h2s": "h2s_hourly",
    "fig_o3": "o3_hourly",
    "fig_o38h": "o3_8h",
    "fig_no2_o3": "no2_vs_o3",
    "fig_pm10": "pm10_hourly",
    "fig_pm25": "pm25_hourly",
    "fig_temp": "temp",
    "fig_rh": "rh",
    "fig_pressure": "pressure",
    "fig_ws": "ws",
    "fig_windrose": "wind_rose",
    "fig_windclassfreq": "wind_class_freq",
}



def _ensure_templates_fresh():
    """Rebuild master templates if assets or the builder changed since the
    last build. Lets logo swaps take effect by simply replacing the PNGs."""
    here = os.path.dirname(os.path.abspath(__file__))
    srcs = [os.path.join(here, "template_builder.py")]
    adir = os.path.join(here, "assets")
    if os.path.isdir(adir):
        srcs += [os.path.join(adir, f) for f in os.listdir(adir)]
    try:
        newest = max(os.path.getmtime(p) for p in srcs if os.path.exists(p))
    except ValueError:
        return
    for tpl, builder in ((TEMPLATE_PATH, "en"), (TEMPLATE_PATH_AR, "ar")):
        if not os.path.exists(tpl) or os.path.getmtime(tpl) < newest:
            try:
                if builder == "en":
                    from report.template_builder import build as _b
                    _b(tpl)
                else:
                    from report.arabize import build_ar as _b
                    _b(tpl)
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    "template auto-rebuild failed", exc_info=True)


def generate_report(
    campaign: Campaign,
    readings: List[Reading],
    limits: List[PollutantLimit],
    out_path: str,
    site_map_path: Optional[str] = None,
    site_photo_path: Optional[str] = None,
    site_photo_paths: Optional[List[str]] = None,
    cover_photo_path: Optional[str] = None,
    calibration_image_paths: Optional[List[str]] = None,
    calibration_items: Optional[List[dict]] = None,
    license_image_paths: Optional[List[str]] = None,
    charts_dir: Optional[str] = None,
    lang: str = "en",
) -> str:
    """Build the report and write the DOCX to out_path. Returns out_path.

    lang: "en" (default), "ar" (full Arabic RTL report), or "bilingual"
    (one file: complete English report followed by the complete Arabic
    report, separated by a section break)."""
    if lang == "bilingual":
        return _generate_bilingual(
            campaign, readings, limits, out_path, site_map_path,
            site_photo_path, cover_photo_path, calibration_image_paths,
            license_image_paths, charts_dir)
    _ensure_templates_fresh()
    summary = build_campaign_summary(campaign, readings, limits)

    # Window-filtered readings for the charts (same filter as the engine).
    w_start = _as_utc(campaign.monitoring_start)
    w_end = _as_utc(campaign.monitoring_end)
    win_readings = [r for r in readings if w_start <= _as_utc(r.timestamp) < w_end]

    limits_map: Dict[Tuple[str, str], float] = {
        (l.pollutant, l.averaging_period): l.limit_ugm3 for l in limits
    }
    charts_dir = charts_dir or tempfile.mkdtemp(prefix="ecoreport_charts_")
    figs = generate_all_charts(
        win_readings, campaign.wind_rose_bins, limits_map, charts_dir,
        window_start=w_start,
        class_frequency_pct=summary.wind_rose.class_frequency_pct,
    )

    template_path = TEMPLATE_PATH_AR if lang == "ar" else TEMPLATE_PATH
    if lang == "ar" and not os.path.exists(template_path):
        from report.arabize import build_ar
        build_ar(template_path)
    tpl = DocxTemplate(template_path)
    ctx = build_context(campaign, summary, lang=lang)

    for ctx_key, fig_key in FIG_MAP.items():
        path = figs.get(fig_key)
        if path and os.path.exists(path):
            width = ROSE_WIDTH_MM if fig_key == "wind_rose" else FIG_WIDTH_MM
            ctx[ctx_key] = InlineImage(tpl, path, width=Mm(width))
        else:
            ctx[ctx_key] = ""

    def _img_list(paths: Optional[List[str]], width_mm: int = 150):
        return [InlineImage(tpl, p, width=Mm(width_mm))
                for p in (paths or []) if os.path.exists(p)]

    # Figure 2 — field photos in a 2x2 grid
    rows = []
    if site_photo_paths:
        imgs = [InlineImage(tpl, p, width=Mm(74)) for p in site_photo_paths
                if p and os.path.exists(p)]
        for i in range(0, len(imgs), 2):
            pair = imgs[i:i + 2]
            if len(pair) == 1:
                pair.append("")
            rows.append(pair)
    ctx["site_photo_rows"] = rows

    # Cover hero band — drawn for this report so the project name is set at
    # the right size and the operator's own photo can be used as the backdrop.
    try:
        from report.cover import build_hero, build_icons
        build_icons()
        hero_dir = charts_dir or os.path.join(os.path.dirname(
            os.path.abspath(out_path)), "charts")
        os.makedirs(hero_dir, exist_ok=True)
        hero_png = os.path.join(hero_dir, f"cover_hero_{lang}.png")
        build_hero(campaign.project_name, hero_png,
                   photo_path=cover_photo_path, lang=lang)
        ctx["cover_hero"] = InlineImage(tpl, hero_png, width=Mm(212))
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("cover hero failed", exc_info=True)
        ctx["cover_hero"] = ""

    ctx["fig_site_map"] = (InlineImage(tpl, site_map_path, width=Mm(150))
                           if site_map_path and os.path.exists(site_map_path)
                           else None)
    ctx["fig_site_photo"] = (InlineImage(tpl, site_photo_path, width=Mm(150))
                             if site_photo_path and os.path.exists(site_photo_path)
                             else None)
    ctx["cover_photo"] = (InlineImage(tpl, cover_photo_path, width=Mm(150))
                          if cover_photo_path and os.path.exists(cover_photo_path)
                          else None)
    ctx["calibration_images"] = [
        {"title": (c.get("title") or "Calibration certificate"),
         "image": InlineImage(tpl, c["path"], width=Mm(150))}
        for c in (calibration_items or [])
        if c.get("path") and os.path.exists(c["path"])]
    ctx["license_images"] = _img_list(license_image_paths)

    # autoescape: "<" is a reserved XML character. Without escaping, a value
    # such as "<5.0" (below detection limit) is silently swallowed by Word.
    tpl.render(ctx, autoescape=True)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tpl.save(out_path)
    return out_path


def _generate_bilingual(campaign, readings, limits, out_path, site_map_path,
                        site_photo_path, cover_photo_path,
                        calibration_image_paths, license_image_paths,
                        charts_dir) -> str:
    """English report followed by the Arabic report in one DOCX."""
    from docx import Document
    from docxcompose.composer import Composer

    with tempfile.TemporaryDirectory(prefix="ecoreport_bi_") as td:
        en_path = os.path.join(td, "en.docx")
        ar_path = os.path.join(td, "ar.docx")
        for lg, pth in (("en", en_path), ("ar", ar_path)):
            generate_report(
                campaign, readings, limits, pth,
                site_map_path=site_map_path, site_photo_path=site_photo_path,
                cover_photo_path=cover_photo_path,
                calibration_image_paths=calibration_image_paths,
                license_image_paths=license_image_paths,
                charts_dir=charts_dir, lang=lg)
        master = Document(en_path)
        master.add_page_break()
        composer = Composer(master)
        composer.append(Document(ar_path))
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        composer.save(out_path)
    return out_path


def convert_to_pdf(docx_path: str, out_dir: Optional[str] = None) -> str:
    """High-quality PDF via LibreOffice (required on the server; Arabic fonts
    Amiri / Noto Sans Arabic must be installed for correct RTL rendering)."""
    import shutil
    import subprocess

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError(
            "LibreOffice is required for PDF conversion but was not found. "
            "Install it (e.g. `apt-get install libreoffice fonts-hosny-amiri "
            "fonts-noto-core`) and retry.")
    out_dir = out_dir or os.path.dirname(os.path.abspath(docx_path))
    pdf_path = os.path.join(
        out_dir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf")

    # Preferred path: UNO bridge — updates TOC / List of Figures / List of
    # Tables before export so index pages are populated in the PDF.
    try:
        subprocess.run(
            [sys.executable, "-m", "report.uno_pdf", docx_path, pdf_path],
            check=True, capture_output=True, timeout=420,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if os.path.exists(pdf_path):
            return pdf_path
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning(
            "UNO PDF path failed — falling back to plain conversion "
            "(TOC pages may be empty)", exc_info=True)

    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", out_dir,
         docx_path],
        check=True, capture_output=True, timeout=300)
    if not os.path.exists(pdf_path):
        raise RuntimeError("PDF conversion produced no output file.")
    return pdf_path
