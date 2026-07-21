"""Phase 6 endpoints — audit trail, report version history, searchable archive.

- GET /campaigns/{id}/audit      -> audit trail for one campaign (incl. its
                                    readings and reports)
- GET /audit                     -> global recent activity (filters: action,
                                    user, entity_type, limit)
- GET /reports/{report_id}/download -> re-download any previously generated
                                    report version from disk
- GET /search?q=...              -> search the archive: campaigns by project
                                    name, client, site name or report number,
                                    each with its report history summary
"""
from __future__ import annotations

import os
import re
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from db import db
import storage

router = APIRouter(tags=["history"])


@router.get("/campaigns/{campaign_id}/audit")
async def campaign_audit(campaign_id: str, limit: int = Query(200, le=1000)):
    """All audit entries touching this campaign: the campaign itself, its
    readings, and every report generated for it."""
    report_ids = [d["id"] async for d in db.report_logs.find(
        {"campaign_id": campaign_id, "id": {"$exists": True}}, {"_id": 0, "id": 1})]
    query = {"$or": [
        {"entity_id": campaign_id},
        {"details.campaign_id": campaign_id},
        {"entity_id": {"$in": report_ids}} if report_ids else {"entity_id": None},
    ]}
    docs = await db.audit_logs.find(query, {"_id": 0}) \
        .sort("timestamp", -1).to_list(length=limit)
    return docs


@router.get("/audit")
async def global_audit(
    action: Optional[str] = None,
    user: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = Query(100, le=1000),
):
    query = {}
    if action:
        query["action"] = action
    if user:
        query["user"] = user
    if entity_type:
        query["entity_type"] = entity_type
    docs = await db.audit_logs.find(query, {"_id": 0}) \
        .sort("timestamp", -1).to_list(length=limit)
    return docs


@router.get("/reports/{report_id}/download")
async def download_report(report_id: str):
    doc = await db.report_logs.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Report version not found")
    path = storage.fetch_report(doc)
    if not path:
        raise HTTPException(
            status_code=410,
            detail=("Report file is no longer available — it was stored on "
                    "local disk only and the server has been redeployed since "
                    "it was generated. Enable S3 cloud storage "
                    "(STORAGE_BACKEND=s3) so future reports survive "
                    "redeploys, and regenerate this report."))
    media = ("application/pdf" if doc.get("format") == "pdf" else
             "application/vnd.openxmlformats-officedocument"
             ".wordprocessingml.document")
    return FileResponse(path, media_type=media, filename=doc["filename"])


@router.get("/search")
async def search_archive(q: str = Query(..., min_length=1),
                         limit: int = Query(50, le=200)):
    """Case-insensitive search across the project archive."""
    rx = {"$regex": re.escape(q.strip()), "$options": "i"}
    campaigns = await db.campaigns.find(
        {"$or": [{"project_name": rx}, {"client": rx}, {"site_name": rx},
                 {"report_number": rx}]},
        {"_id": 0},
    ).sort("created_at", -1).to_list(length=limit)

    ids = [c["id"] for c in campaigns]
    counts: dict = {}
    latest: dict = {}
    if ids:
        pipeline = [
            {"$match": {"campaign_id": {"$in": ids}}},
            {"$sort": {"generated_at": -1}},
            {"$group": {"_id": "$campaign_id", "n": {"$sum": 1},
                        "latest": {"$first": "$$ROOT"}}},
        ]
        async for row in db.report_logs.aggregate(pipeline):
            counts[row["_id"]] = row["n"]
            lt = row["latest"]
            lt.pop("_id", None)
            latest[row["_id"]] = {k: lt.get(k) for k in
                                  ("id", "version", "lang", "format",
                                   "filename", "generated_at", "generated_by")}
    results = []
    for c in campaigns:
        results.append({
            "campaign": c,
            "report_count": counts.get(c["id"], 0),
            "latest_report": latest.get(c["id"]),
        })
    return {"query": q, "count": len(results), "results": results}
