"""Client portal — read-only share links, and the home dashboard feed.

A share link lets a client download the reports for one campaign without an
account. Security model:

* the link carries a **signed JWT** (same secret as login, but a distinct
  ``typ`` claim so a share token can never be used as a session, and a
  session token can never open a portal);
* every link is also a **row in the database**, so it can be revoked
  immediately and every download is counted;
* links **expire** — 30 days by default, set per link;
* the portal exposes only the campaign's own reports: no readings, no audit
  trail, no other campaigns, and no way to enumerate them, because the
  campaign is read from the signed token rather than from the URL path.

The portal endpoints are deliberately registered WITHOUT the login
dependency; everything else in the app stays behind authentication.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import storage
from audit import audit
from auth import JWT_ALG, JWT_SECRET, current_user, current_username
from db import db, to_mongo

SHARE_TYP = "share"

router = APIRouter(tags=["portal"])          # protected: link management
public = APIRouter(prefix="/portal", tags=["portal"])   # open: client access


# ---------------------------------------------------------------------------
# Link management (requires login)
# ---------------------------------------------------------------------------
class ShareCreate(BaseModel):
    campaign_id: str
    recipient: Optional[str] = Field(default=None, max_length=160)
    days_valid: int = Field(default=30, ge=1, le=365)


def _sign(share_id: str, campaign_id: str, expires: datetime) -> str:
    return jwt.encode(
        {"typ": SHARE_TYP, "sid": share_id, "cid": campaign_id,
         "exp": expires, "iat": datetime.now(timezone.utc)},
        JWT_SECRET, algorithm=JWT_ALG)


@router.post("/shares", status_code=status.HTTP_201_CREATED)
async def create_share(payload: ShareCreate,
                       user: str = Depends(current_username)):
    campaign = await db.campaigns.find_one({"id": payload.campaign_id},
                                           {"_id": 0})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    share_id = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(days=payload.days_valid)
    token = _sign(share_id, payload.campaign_id, expires)
    doc = {
        "id": share_id,
        "campaign_id": payload.campaign_id,
        "project_name": campaign.get("project_name"),
        "recipient": payload.recipient,
        "created_by": user,
        "created_at": datetime.now(timezone.utc),
        "expires_at": expires,
        "revoked": False,
        "views": 0,
        "downloads": 0,
    }
    await db.shares.insert_one(to_mongo(dict(doc)))
    await audit("share.create", "campaign", payload.campaign_id, user,
                {"share_id": share_id, "recipient": payload.recipient,
                 "days_valid": payload.days_valid})
    doc["token"] = token
    return doc


@router.get("/campaigns/{campaign_id}/shares")
async def list_shares(campaign_id: str):
    docs = await db.shares.find({"campaign_id": campaign_id}, {"_id": 0}) \
        .sort("created_at", -1).to_list(length=100)
    now = datetime.now(timezone.utc)
    for d in docs:
        exp = d.get("expires_at")
        if isinstance(exp, str):
            exp = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        if exp and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        d["expired"] = bool(exp and exp < now)
        # tokens are never returned again — re-issue a link instead
        d.pop("token", None)
    return docs


@router.delete("/shares/{share_id}", status_code=204)
async def revoke_share(share_id: str,
                       user: str = Depends(current_username)) -> Response:
    doc = await db.shares.find_one({"id": share_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.shares.update_one({"id": share_id}, {"$set": {"revoked": True}})
    await audit("share.revoke", "campaign", doc["campaign_id"], user,
                {"share_id": share_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Public portal (no login)
# ---------------------------------------------------------------------------
async def _resolve(token: str) -> dict:
    """Validate a share token and return its database row."""
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=410,
                            detail="This link has expired. Please ask for a new one.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=404, detail="This link is not valid.")
    if claims.get("typ") != SHARE_TYP:
        raise HTTPException(status_code=404, detail="This link is not valid.")
    doc = await db.shares.find_one({"id": claims.get("sid")}, {"_id": 0})
    if not doc or doc.get("revoked"):
        raise HTTPException(status_code=410,
                            detail="This link has been withdrawn.")
    if doc["campaign_id"] != claims.get("cid"):
        raise HTTPException(status_code=404, detail="This link is not valid.")
    return doc


@public.get("/{token}")
async def portal_view(token: str):
    """What the client sees: the project's details and its report versions."""
    share = await _resolve(token)
    campaign = await db.campaigns.find_one({"id": share["campaign_id"]},
                                           {"_id": 0})
    if not campaign:
        raise HTTPException(status_code=404, detail="Project not found")

    reports = await db.report_logs.find(
        {"campaign_id": share["campaign_id"], "id": {"$exists": True}},
        {"_id": 0}).sort("generated_at", -1).to_list(length=100)

    await db.shares.update_one({"id": share["id"]}, {"$inc": {"views": 1}})

    return {
        "project": {
            "name": campaign.get("project_name"),
            "client": campaign.get("client"),
            "site": campaign.get("site_name"),
            "report_number": campaign.get("report_number"),
            "monitoring_start": campaign.get("monitoring_start"),
            "monitoring_end": campaign.get("monitoring_end"),
        },
        "provider": {
            "name": campaign.get("provider", "Bander Said Allehiany (BSA)"),
        },
        "expires_at": share.get("expires_at"),
        "reports": [
            {"id": r["id"], "version": r.get("version"),
             "lang": r.get("lang", "en"), "format": r.get("format", "docx"),
             "filename": r.get("filename"),
             "generated_at": r.get("generated_at"),
             "size_bytes": r.get("size_bytes")}
            for r in reports
        ],
    }


@public.get("/{token}/reports/{report_id}")
async def portal_download(token: str, report_id: str):
    share = await _resolve(token)
    doc = await db.report_logs.find_one({"id": report_id}, {"_id": 0})
    # the report must belong to the campaign this link was issued for
    if not doc or doc.get("campaign_id") != share["campaign_id"]:
        raise HTTPException(status_code=404, detail="Report not found")
    path = storage.fetch_report(doc)
    if not path:
        raise HTTPException(
            status_code=410,
            detail="This file is no longer available. Please contact the "
                   "consultancy for a fresh copy.")
    await db.shares.update_one({"id": share["id"]}, {"$inc": {"downloads": 1}})
    media = ("application/pdf" if doc.get("format") == "pdf" else
             "application/vnd.openxmlformats-officedocument"
             ".wordprocessingml.document")
    return FileResponse(path, media_type=media, filename=doc["filename"])


# ---------------------------------------------------------------------------
# Home dashboard feed (requires login)
# ---------------------------------------------------------------------------
@router.get("/dashboard")
async def home_dashboard(user: dict = Depends(current_user)):
    """Everything the landing page needs, in one call."""
    campaigns = await db.campaigns.find({}, {"_id": 0}) \
        .sort("created_at", -1).to_list(length=500)
    reports = await db.report_logs.find({}, {"_id": 0}) \
        .sort("generated_at", -1).to_list(length=20)

    reported = set()
    async for r in db.report_logs.aggregate(
            [{"$group": {"_id": "$campaign_id"}}]):
        reported.add(r["_id"])

    with_data = set()
    async for r in db.readings.aggregate(
            [{"$group": {"_id": "$campaign_id", "n": {"$sum": 1}}}]):
        if r["n"]:
            with_data.add(r["_id"])

    needs_attention = [
        {"id": c["id"], "project_name": c.get("project_name"),
         "client": c.get("client"),
         "reason": ("data uploaded, no report generated"
                    if c["id"] in with_data else "no data uploaded")}
        for c in campaigns
        if c["id"] not in reported
    ][:8]

    activity = await db.audit_logs.find({}, {"_id": 0}) \
        .sort("timestamp", -1).to_list(length=8)

    return {
        "counts": {
            "campaigns": len(campaigns),
            "with_data": len(with_data),
            "reported": len(reported),
            "reports": await db.report_logs.count_documents({}),
        },
        "recent_campaigns": [
            {"id": c["id"], "project_name": c.get("project_name"),
             "client": c.get("client"), "site_name": c.get("site_name"),
             "created_at": c.get("created_at"),
             "has_data": c["id"] in with_data,
             "has_report": c["id"] in reported}
            for c in campaigns[:6]
        ],
        "recent_reports": [
            {"id": r.get("id"), "campaign_id": r.get("campaign_id"),
             "project_name": r.get("project_name"),
             "version": r.get("version"), "lang": r.get("lang"),
             "format": r.get("format"), "filename": r.get("filename"),
             "generated_at": r.get("generated_at"),
             "generated_by": r.get("generated_by")}
            for r in reports[:6]
        ],
        "needs_attention": needs_attention,
        "activity": activity,
    }
