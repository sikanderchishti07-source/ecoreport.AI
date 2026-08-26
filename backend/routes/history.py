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
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from auth import require_admin
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
async def download_report(report_id: str,
                          user: dict = Depends(require_admin)):
    """Admin only. Field operators generate and read reports on screen but
    never take the file off the system — see routes/review.py. Hiding the
    button would not be a control; this is the check that matters."""
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
    # The readable name where the record carries one. Reports generated
    # before this existed have only the stored name, so that is the
    # fallback and nothing in the archive becomes undownloadable.
    return FileResponse(path, media_type=media,
                        filename=doc.get("download_name") or doc["filename"])



# ---------------------------------------------------------------------------
# The reports archive
#
# Every issued report has always been recorded, but only ever reachable
# through the campaign that produced it. Answering "what did we issue in
# July", "everything for SAJCO", or "which reports are still in review" meant
# remembering which campaign each one belonged to.
#
# This joins the report log to its campaign and returns one row per version.
# Read-only: it writes nothing, so it cannot disturb anything it reads.
# ---------------------------------------------------------------------------
@router.get("/reports")
async def list_reports(
    q: Optional[str] = Query(None, description="report number, project or client"),
    client_id: Optional[str] = Query(None),
    campaign_type: Optional[str] = Query(None),
    month: Optional[str] = Query(None, description="YYYY-MM"),
    status: Optional[str] = Query(None),
    limit: int = Query(200, le=1000),
):
    """One row per issued report version, newest first.

    Every version is its own row rather than only the latest. Where a Rev 01
    corrected something in a Rev 00, both were sent to a client and both have
    to be findable; an archive that hides what it superseded is not an
    archive.
    """
    logs = await db.report_logs.find({}, {"_id": 0}) \
        .sort("generated_at", -1).to_list(length=2000)
    if not logs:
        return {"count": 0, "total": 0, "reports": [], "stats": _empty_stats()}

    ids = sorted({d.get("campaign_id") for d in logs if d.get("campaign_id")})
    camp_docs = await db.campaigns.find(
        {"id": {"$in": ids}},
        {"_id": 0, "id": 1, "project_name": 1, "client": 1, "client_id": 1,
         "site_name": 1, "campaign_type": 1, "status": 1, "report_number": 1,
         "revision": 1},
    ).to_list(length=len(ids) or 1)
    campaigns = {c["id"]: c for c in camp_docs}

    # The recorded legal name where a campaign is linked, the typed text
    # where it is not — the same rule the report itself follows.
    linked = sorted({c.get("client_id") for c in camp_docs if c.get("client_id")})
    names: Dict[str, str] = {}
    if linked:
        for doc in await db.clients.find(
            {"id": {"$in": linked}},
            {"_id": 0, "id": 1, "legal_name": 1, "short_name": 1},
        ).to_list(length=len(linked)):
            names[doc["id"]] = doc.get("legal_name") or doc.get("short_name") or ""

    rows = []
    for d in logs:
        c = campaigns.get(d.get("campaign_id"))
        if c is None:
            # The campaign was deleted after the report was issued. The report
            # is still a record of something that went to a client, so it is
            # listed rather than dropped — silently.
            c = {}
        client_name = (names.get(c.get("client_id") or "")
                       or c.get("client") or "\u2014")
        # The log keeps the project name as it stood when the report was
        # generated; the campaign holds it as it stands now. The printed name
        # is what the report actually carries, so that is shown — but a
        # search has to match either, or a renamed project becomes
        # unfindable by the name everything else in the app calls it.
        printed_name = d.get("project_name") or c.get("project_name") or "\u2014"
        current_name = c.get("project_name") or ""
        rows.append({
            "id": d.get("id"),
            "campaign_id": d.get("campaign_id"),
            "campaign_deleted": not campaigns.get(d.get("campaign_id")),
            "report_number": c.get("report_number") or "\u2014",
            "project_name": printed_name,
            "current_project_name": current_name,
            "site_name": c.get("site_name") or "",
            "client": client_name,
            "client_id": c.get("client_id"),
            # No default. A report whose campaign has been deleted has no
            # known type, and calling it air would put it under a filter it
            # may not belong to.
            "campaign_type": c.get("campaign_type"),
            "status": c.get("status") or "draft",
            "version": d.get("version"),
            "format": d.get("format") or "docx",
            "lang": d.get("lang") or "en",
            "filename": d.get("filename"),
            "generated_at": d.get("generated_at"),
            "generated_by": d.get("generated_by"),
            "size_bytes": d.get("size_bytes"),
        })

    stats = _report_stats(rows)

    def keep(r) -> bool:
        if client_id and r["client_id"] != client_id:
            return False
        if campaign_type and r["campaign_type"] != campaign_type:
            return False
        if status and r["status"] != status:
            return False
        if month and not str(r.get("generated_at") or "").startswith(month):
            return False
        if q:
            needle = q.strip().lower()
            haystack = " ".join(str(r.get(k) or "") for k in
                                ("report_number", "project_name",
                                 "current_project_name", "client",
                                 "site_name", "filename"))
            if needle not in haystack.lower():
                return False
        return True

    filtered = [r for r in rows if keep(r)]
    return {
        "count": len(filtered),
        "total": len(rows),
        "reports": filtered[:limit],
        "stats": stats,
    }


def _empty_stats() -> Dict[str, int]:
    return {"total": 0, "this_month": 0, "in_review": 0, "approved": 0}


def _report_stats(rows: List[dict]) -> Dict[str, int]:
    """Counts over every report, not the filtered view.

    A total that changed as filters were applied would answer a different
    question each time it was read.
    """
    this_month = datetime.now(timezone.utc).strftime("%Y-%m")
    return {
        "total": len(rows),
        "this_month": sum(1 for r in rows
                          if str(r.get("generated_at") or "").startswith(this_month)),
        "in_review": sum(1 for r in rows if r["status"] in ("in_review", "submitted")),
        "approved": sum(1 for r in rows if r["status"] == "approved"),
    }

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
