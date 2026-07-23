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
