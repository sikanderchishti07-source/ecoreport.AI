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

    # Version number: sequential per campaign across all languages/formats
    version = await db.report_logs.count_documents(
        {"campaign_id": campaign_id}) + 1
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = f"AAQ_Report_{campaign_id[:8]}_v{version:03d}_{lang}_{ts}.docx"
    out_path = os.path.join(REPORT_DIR, campaign_id, fname)

    try:
        generate_report(campaign, readings, limits, out_path, lang=lang)
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
