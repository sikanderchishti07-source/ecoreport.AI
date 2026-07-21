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


def generate_report(
    campaign: Campaign,
    readings: List[Reading],
    limits: List[PollutantLimit],
    out_path: str,
    site_map_path: Optional[str] = None,
    site_photo_path: Optional[str] = None,
    cover_photo_path: Optional[str] = None,
    calibration_image_paths: Optional[List[str]] = None,
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

    ctx["fig_site_map"] = (InlineImage(tpl, site_map_path, width=Mm(150))
                           if site_map_path and os.path.exists(site_map_path)
                           else None)
    ctx["fig_site_photo"] = (InlineImage(tpl, site_photo_path, width=Mm(150))
                             if site_photo_path and os.path.exists(site_photo_path)
                             else None)
    ctx["cover_photo"] = (InlineImage(tpl, cover_photo_path, width=Mm(150))
                          if cover_photo_path and os.path.exists(cover_photo_path)
                          else None)
    ctx["calibration_images"] = _img_list(calibration_image_paths)
    ctx["license_images"] = _img_list(license_image_paths)

    tpl.render(ctx)
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
