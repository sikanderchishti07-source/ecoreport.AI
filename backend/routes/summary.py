"""Phase 2 endpoint — GET /api/campaigns/{id}/summary."""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException

from calc import build_campaign_summary
from db import db
from models import Campaign, CampaignSummary, PollutantLimit, Reading

log = logging.getLogger(__name__)

router = APIRouter(tags=["summary"])


@router.get("/campaigns/{campaign_id}/summary", response_model=CampaignSummary)
async def get_campaign_summary(campaign_id: str) -> CampaignSummary:
    campaign_doc = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not campaign_doc:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign = Campaign(**campaign_doc)
    # The engine measures capture and averages against the window, so every
    # figure it produces subtracts one datetime from another. Without a
    # window that is a TypeError several layers down, saying nothing about
    # the cause. The window is set by the upload, so this is reached only
    # before any data has arrived.
    if not campaign.monitoring_start or not campaign.monitoring_end:
        raise HTTPException(
            status_code=400,
            detail=("This campaign has no monitoring window. Upload the data "
                    "file and the window is read from it, or set the start "
                    "and end dates on the campaign."))

    reading_docs = (
        await db.readings.find({"campaign_id": campaign_id}, {"_id": 0})
        .sort("timestamp", 1)
        .to_list(length=100000)
    )
    readings: List[Reading] = [Reading(**d) for d in reading_docs]

    limit_docs = await db.pollutant_limits.find({}, {"_id": 0}).to_list(length=200)
    limits: List[PollutantLimit] = [PollutantLimit(**d) for d in limit_docs]

    return build_campaign_summary(campaign, readings, limits)
