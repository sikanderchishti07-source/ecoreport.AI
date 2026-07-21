"""Phase 3 endpoint — generate and download the AAQ report DOCX."""
from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from db import db, to_mongo
from models import Campaign, PollutantLimit, Reading
from report.generate import generate_report

log = logging.getLogger(__name__)
router = APIRouter(tags=["report"])

REPORT_DIR = os.environ.get("REPORT_DIR", os.path.join(tempfile.gettempdir(), "ecoreport_reports"))


@router.post("/campaigns/{campaign_id}/report")
async def create_report(campaign_id: str):
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

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = f"AAQ_Report_{campaign_id[:8]}_{ts}.docx"
    out_path = os.path.join(REPORT_DIR, campaign_id, fname)

    try:
        generate_report(campaign, readings, limits, out_path)
    except Exception as exc:  # noqa: BLE001
        log.exception("report generation failed")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {exc}")

    # Light version log (full audit trail arrives in Phase 6)
    await db.report_logs.insert_one(to_mongo({
        "campaign_id": campaign_id,
        "filename": fname,
        "path": out_path,
        "generated_at": datetime.now(timezone.utc),
    }))

    return FileResponse(
        out_path,
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document"),
        filename=fname,
    )


@router.get("/campaigns/{campaign_id}/reports")
async def list_reports(campaign_id: str):
    docs = await db.report_logs.find(
        {"campaign_id": campaign_id}, {"_id": 0}
    ).sort("generated_at", -1).to_list(length=100)
    return docs
