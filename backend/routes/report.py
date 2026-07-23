"""Phase 3 endpoint — generate and download the AAQ report DOCX."""
from __future__ import annotations

import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from audit import audit
from auth import current_username
from db import db, to_mongo
import storage
from models import Campaign, PollutantLimit, Reading
from report.generate import convert_to_pdf, generate_report

log = logging.getLogger(__name__)
router = APIRouter(tags=["report"])

REPORT_DIR = os.environ.get("REPORT_DIR", os.path.join(tempfile.gettempdir(), "ecoreport_reports"))


@router.post("/campaigns/{campaign_id}/report")
async def create_report(campaign_id: str, lang: str = "en",
                        format: str = "docx",
                        x_user: str = Depends(current_username)):
    if lang not in ("en", "ar", "bilingual"):
        raise HTTPException(status_code=422,
                            detail="lang must be en, ar, or bilingual")
    if format not in ("docx", "pdf"):
        raise HTTPException(status_code=422,
                            detail="format must be docx or pdf")
    campaign_doc = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not campaign_doc:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign = Campaign(**campaign_doc)

    reading_docs = (
        await db.readings.find({"campaign_id": campaign_id}, {"_id": 0})
        .sort("timestamp", 1).to_list(length=100000)
    )
    if not reading_docs:
        raise HTTPException(status_code=400, detail="No readings ingested for this campaign")
    readings: List[Reading] = [Reading(**d) for d in reading_docs]

    limit_docs = await db.pollutant_limits.find({}, {"_id": 0}).to_list(length=200)
    limits: List[PollutantLimit] = [PollutantLimit(**d) for d in limit_docs]

    # Guard: a report with zero readings inside the monitoring window would be
    # an empty shell of N/R tables and blank charts. Fail early with the exact
    # mismatch so the user can fix the campaign dates or re-upload the data.
    from calc import _as_utc
    w_start, w_end = _as_utc(campaign.monitoring_start), _as_utc(campaign.monitoring_end)
    in_window = sum(1 for r in readings if w_start <= _as_utc(r.timestamp) < w_end)
    if in_window == 0:
        d_min = min(_as_utc(r.timestamp) for r in readings)
        d_max = max(_as_utc(r.timestamp) for r in readings)
        fmt = "%d %b %Y %H:%M"
        raise HTTPException(
            status_code=400,
            detail=(f"No readings fall inside this campaign's monitoring window. "
                    f"Your uploaded data covers {d_min.strftime(fmt)} to "
                    f"{d_max.strftime(fmt)} (UTC), but the campaign window is "
                    f"{w_start.strftime(fmt)} to {w_end.strftime(fmt)}. "
                    f"Edit the campaign's monitoring start/end dates to match "
                    f"the data (or re-upload the correct file), then generate "
                    f"again."))
    total_hours = max(int((w_end - w_start).total_seconds() // 3600), 1)
    if in_window < 0.05 * total_hours:
        log.warning("report window covers only %s readings of %s window hours",
                    in_window, total_hours)

    # Version number: sequential per campaign across all languages/formats
    version = await db.report_logs.count_documents(
        {"campaign_id": campaign_id}) + 1
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = f"AAQ_Report_{campaign_id[:8]}_v{version:03d}_{lang}_{ts}.docx"
    out_path = os.path.join(REPORT_DIR, campaign_id, fname)

    # Attachments: field photos (Figure 2), certificates (Appendix 3),
    # licence (Appendix 4), operator site-map override (Figure 1).
    atts = await db.attachments.find({"campaign_id": campaign_id}, {"_id": 0}) \
        .sort([("order", 1), ("uploaded_at", 1)]).to_list(length=500)
    by_kind: dict = {}
    for a in atts:
        by_kind.setdefault(a["kind"], []).append(a)

    site_photos = [a["path"] for a in by_kind.get("site_photo", [])
                   if os.path.exists(a.get("path", ""))]
    licence = [a["path"] for a in by_kind.get("license", [])
               if os.path.exists(a.get("path", ""))]
    cover = next((a["path"] for a in by_kind.get("cover_photo", [])
                  if os.path.exists(a.get("path", ""))), None)

    def _as_dict(i):
        return i if isinstance(i, dict) else i.model_dump()
    sn_map = {_as_dict(i).get("sn"): _as_dict(i)
              for i in (campaign.instruments or [])}
    cal_items = []
    for a in by_kind.get("calibration", []):
        if not os.path.exists(a.get("path", "")):
            continue
        instr = sn_map.get(a.get("instrument_sn"))
        if instr:
            title = (f"Calibration certificate — {instr.get('technique','')} "
                     f"({instr.get('parameter','')}), S/N {instr.get('sn','')}")
        else:
            title = a.get("caption") or "Calibration certificate"
        cal_items.append({"title": title.strip(" —"), "path": a["path"]})

    # Figure 1 — satellite site map (operator upload wins over the auto map)
    site_map = next((a["path"] for a in by_kind.get("site_map", [])
                     if os.path.exists(a.get("path", ""))), None)
    if not site_map:
        try:
            from report.sitemap import fetch_site_map
            site_map = fetch_site_map(
                campaign.latitude, campaign.longitude,
                os.path.join(REPORT_DIR, campaign_id, "site_map.png"))
        except Exception:  # noqa: BLE001
            log.warning("automatic site map unavailable", exc_info=True)
            site_map = None

    try:
        generate_report(campaign, readings, limits, out_path, lang=lang,
                        site_map_path=site_map,
                        site_photo_paths=site_photos,
                        cover_photo_path=cover,
                        calibration_items=cal_items,
                        license_image_paths=licence)
        if format == "pdf":
            out_path = convert_to_pdf(out_path)
            fname = os.path.basename(out_path)
    except Exception as exc:  # noqa: BLE001
        log.exception("report generation failed")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {exc}")

    storage_meta = storage.store_report(out_path, campaign_id, fname)
    report_id = str(uuid.uuid4())
    await db.report_logs.insert_one(to_mongo({
        "id": report_id,
        "storage": storage_meta["storage"],
        "s3_key": storage_meta["s3_key"],
        "campaign_id": campaign_id,
        "project_name": campaign.project_name,
        "version": version,
        "filename": fname,
        "path": out_path,
        "lang": lang,
        "format": format,
        "generated_by": x_user,
        "generated_at": datetime.now(timezone.utc),
        "readings_count": len(readings),
        "size_bytes": os.path.getsize(out_path),
    }))
    await audit("report.generate", "report", report_id, x_user,
                {"campaign_id": campaign_id, "version": version,
                 "lang": lang, "format": format, "filename": fname})

    media = ("application/pdf" if format == "pdf" else
             "application/vnd.openxmlformats-officedocument"
             ".wordprocessingml.document")
    return FileResponse(out_path, media_type=media, filename=fname)


@router.get("/campaigns/{campaign_id}/reports")
async def list_reports(campaign_id: str):
    docs = await db.report_logs.find(
        {"campaign_id": campaign_id}, {"_id": 0}
    ).sort("generated_at", -1).to_list(length=100)
    return docs


@router.get("/campaigns/{campaign_id}/report-preview")
async def preview_report(campaign_id: str):
    """Everything the report will say, without building the document.

    Lets the operator check the figures, the compliance verdicts and the
    readiness warnings in the browser before spending a minute on generation.
    """
    campaign_doc = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not campaign_doc:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign = Campaign(**campaign_doc)

    reading_docs = await db.readings.find(
        {"campaign_id": campaign_id}, {"_id": 0}).sort("timestamp", 1) \
        .to_list(length=None)
    readings = [Reading(**d) for d in reading_docs]
    if not readings:
        raise HTTPException(status_code=400,
                            detail="No readings uploaded for this campaign")

    limit_docs = await db.pollutant_limits.find({}, {"_id": 0}).to_list(length=200)
    limits = [PollutantLimit(**d) for d in limit_docs]

    from calc import _as_utc, build_campaign_summary
    w_start, w_end = _as_utc(campaign.monitoring_start), _as_utc(campaign.monitoring_end)
    in_window = sum(1 for r in readings if w_start <= _as_utc(r.timestamp) < w_end)

    blockers, warnings = [], []
    if in_window == 0:
        d_min = min(_as_utc(r.timestamp) for r in readings)
        d_max = max(_as_utc(r.timestamp) for r in readings)
        fmt = "%d %b %Y %H:%M"
        blockers.append(
            f"No readings fall inside the monitoring window. Your data covers "
            f"{d_min.strftime(fmt)} to {d_max.strftime(fmt)}, but the window is "
            f"{w_start.strftime(fmt)} to {w_end.strftime(fmt)}.")
        return {"ready": False, "blockers": blockers, "warnings": [],
                "sections": [], "summary": None}

    summary = build_campaign_summary(campaign, readings, limits)

    if (summary.overall_hourly_capture_pct or 0) < 75:
        warnings.append(
            f"Overall data capture is {summary.overall_hourly_capture_pct:.1f}%, "
            f"below the 75% requirement. Affected parameters will print as "
            f"N/R* (not reportable).")
    not_reportable = [p.pollutant for p in summary.pollutants
                      if not p.is_supporting and (p.hourly_capture_pct or 0) < 75]
    if not_reportable:
        warnings.append("Not reportable at hourly resolution: "
                        + ", ".join(not_reportable))

    atts = await db.attachments.find({"campaign_id": campaign_id},
                                     {"_id": 0}).to_list(length=500)
    kinds = {}
    for a in atts:
        kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
    if not kinds.get("site_photo"):
        warnings.append("No field photos uploaded — Figure 2 will be empty.")
    if not kinds.get("calibration"):
        warnings.append("No calibration certificates uploaded — Appendix 3 "
                        "will be empty.")
    if not campaign.instruments:
        warnings.append("No instruments set — Table 4 will fall back to the "
                        "default list. Load a mobile lab on the Instruments tab.")
    if not campaign.report_number:
        warnings.append("Report number is blank.")

    def pol_row(p):
        periods = [{
            "period": e.averaging_period,
            "limit": e.limit_ugm3,
            "capture_pct": round(e.capture_pct, 1),
            "exceedances": e.exceedance_count,
            "verdict": e.verdict,
        } for e in p.period_evaluations]
        return {
            "pollutant": p.pollutant,
            "supporting": p.is_supporting,
            "capture_pct": round(p.hourly_capture_pct or 0, 1),
            "max": p.hourly_max, "min": p.hourly_min, "mean": p.hourly_mean,
            "mdl": p.mdl_ugm3, "below_mdl": p.below_mdl_count,
            "periods": periods,
        }

    exceedances = sum(e.exceedance_count for p in summary.pollutants
                      for e in p.period_evaluations)
    sections = [
        {"title": "Executive summary", "figures": 1, "tables": 1},
        {"title": "Monitoring and data collection", "figures": 2, "tables": 3},
        {"title": "Ambient air quality standards", "figures": 0, "tables": 1},
        {"title": "Calibration and maintenance", "figures": 0, "tables": 0},
        {"title": "Results and discussion", "figures": 16, "tables": 10},
        {"title": "Conclusions", "figures": 0, "tables": 0},
        {"title": "Appendices", "figures": kinds.get("calibration", 0), "tables": 0},
    ]

    return {
        "ready": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "campaign": {
            "project_name": campaign.project_name,
            "client": campaign.client,
            "site_name": campaign.site_name,
            "report_number": campaign.report_number,
            "revision": campaign.revision,
            "window": f"{w_start.strftime('%d %b %Y %H:%M')} — "
                      f"{w_end.strftime('%d %b %Y %H:%M')}",
        },
        "headline": {
            "monitoring_hours": summary.monitoring_hours,
            "capture_pct": round(summary.overall_hourly_capture_pct or 0, 1),
            "readings_in_window": in_window,
            "exceedances": exceedances,
            "prevailing_wind": summary.wind_rose.prevailing_direction,
            "instruments": len(campaign.instruments or []),
            "attachments": kinds,
        },
        "pollutants": [pol_row(p) for p in summary.pollutants],
        "sections": sections,
    }
