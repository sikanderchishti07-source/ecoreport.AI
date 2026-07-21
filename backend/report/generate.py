"""Phase 3 orchestrator — render the full AAQ report DOCX for a campaign.

Pipeline: readings + limits -> CampaignSummary (calc.py) -> charts (charts.py)
-> context (context.py) -> docxtpl render of master_template.docx.
Charts are regenerated from the raw data on every call.
"""
from __future__ import annotations

import os
import tempfile
from typing import Dict, List, Optional, Tuple

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

from calc import build_campaign_summary, _as_utc
from models import Campaign, PollutantLimit, Reading
from report.charts import generate_all_charts
from report.context import build_context

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "master_template.docx")

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
) -> str:
    """Build the report and write the DOCX to out_path. Returns out_path."""
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

    tpl = DocxTemplate(TEMPLATE_PATH)
    ctx = build_context(campaign, summary)

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
