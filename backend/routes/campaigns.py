"""Campaign CRUD endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Header, HTTPException, Response, status

from audit import audit, diff_fields
from db import db, from_mongo, to_mongo
from models import Campaign, CampaignCreate, CampaignUpdate

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.post("", response_model=Campaign, status_code=status.HTTP_201_CREATED)
async def create_campaign(payload: CampaignCreate,
                          x_user: str = Header(default="system")) -> Campaign:
    campaign = Campaign(**payload.model_dump())
    await db.campaigns.insert_one(to_mongo(campaign.model_dump()))
    await audit("campaign.create", "campaign", campaign.id, x_user,
                {"project_name": campaign.project_name,
                 "client": campaign.client})
    return campaign


@router.get("", response_model=List[Campaign])
async def list_campaigns() -> List[Campaign]:
    cursor = db.campaigns.find({}, {"_id": 0}).sort("created_at", -1)
    docs = await cursor.to_list(length=1000)
    # Attach reading counts (skeleton: cheap because we also track it lazily).
    ids = [d["id"] for d in docs]
    counts: dict[str, int] = {}
    if ids:
        pipeline = [
            {"$match": {"campaign_id": {"$in": ids}}},
            {"$group": {"_id": "$campaign_id", "n": {"$sum": 1}}},
        ]
        async for row in db.readings.aggregate(pipeline):
            counts[row["_id"]] = row["n"]
    for d in docs:
        d["reading_count"] = counts.get(d["id"], 0)
    return [Campaign(**d) for d in docs]


@router.get("/{campaign_id}", response_model=Campaign)
async def get_campaign(campaign_id: str) -> Campaign:
    doc = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Campaign not found")
    doc["reading_count"] = await db.readings.count_documents({"campaign_id": campaign_id})
    return Campaign(**doc)


@router.put("/{campaign_id}", response_model=Campaign)
async def update_campaign(campaign_id: str, payload: CampaignUpdate,
                          x_user: str = Header(default="system")) -> Campaign:
    existing = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Campaign not found")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return Campaign(**existing)

    updates["updated_at"] = datetime.now(timezone.utc)
    await db.campaigns.update_one({"id": campaign_id}, {"$set": to_mongo(updates)})
    fresh = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    changes = diff_fields(existing, updates)
    if changes:
        await audit("campaign.update", "campaign", campaign_id, x_user,
                    {"changes": changes})
    fresh["reading_count"] = await db.readings.count_documents({"campaign_id": campaign_id})
    return Campaign(**fresh)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_campaign(campaign_id: str,
                          x_user: str = Header(default="system")) -> Response:
    existing = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    res = await db.campaigns.delete_one({"id": campaign_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Campaign not found")
    # cascade (report history and audit logs are intentionally preserved)
    await db.readings.delete_many({"campaign_id": campaign_id})
    await db.upload_logs.delete_many({"campaign_id": campaign_id})
    await audit("campaign.delete", "campaign", campaign_id, x_user,
                {"project_name": (existing or {}).get("project_name")})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
