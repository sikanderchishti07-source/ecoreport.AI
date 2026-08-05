"""Review workflow — field operator submits, reviewing engineer signs off.

Why this exists
---------------
Reports carry BSA's stamp. Until now anyone with an account could generate a
report and hand it to a client. This puts one person between the field work
and the client:

* a **field operator** (role ``member``) enters the campaign, uploads the
  readings, generates the report and reads it on screen — but cannot take the
  file off the system;
* a **reviewing engineer** (role ``admin``) is told when something is waiting,
  downloads it, and either approves it or sends it back with a comment.

The three doors
---------------
Blocking a button in the browser is not a control — the URL still works. The
file can leave the system by exactly three routes, and all three are closed to
operators in code, not in the interface:

1. ``POST /campaigns/{id}/report`` returns the generated file directly.
   Operators still generate; they receive the version record instead of the
   bytes.
2. ``GET /reports/{id}/download`` re-downloads any stored version.
3. ``POST /shares`` mints a client-portal link that needs no login at all.
   This is the one that is easy to forget, and it would have made the other
   two pointless.

Status
------
``submitted`` and ``approved`` join the existing draft / ingested / ready /
archived. Returning a campaign puts it back to ``ready``, so a correction and
a resubmission are the ordinary path rather than an exception. There is no
limit on rounds.

Submitting does not lock the campaign. The report is rebuilt from live data
whenever it is generated, so freezing the readings at submission would mean
every small correction needed the reviewer to unlock it first.

Notifications are rows in ``notifications``, read by the bell in the header.
Sending mail is deliberately a separate stage: it needs an address on every
user account and an SMTP mailbox, and neither should hold this up.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from audit import audit
from auth import current_user, require_admin
from db import db, to_mongo

log = logging.getLogger(__name__)
router = APIRouter(tags=["review"])

SUBMITTED = "submitted"
APPROVED = "approved"
READY = "ready"


class ReviewNote(BaseModel):
    comment: Optional[str] = Field(default=None, max_length=2000)


class SubmitPayload(ReviewNote):
    # Which generated version is being submitted. A campaign accumulates
    # versions — seventeen is not unusual — so "this campaign is ready" says
    # nothing useful on its own. The reviewer must know which document they
    # are signing off, and it must not change under them afterwards.
    report_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Notification plumbing
# ---------------------------------------------------------------------------
async def _notify(recipient_id: str, kind: str, message: str,
                  campaign_id: str, project_name: str, actor: str) -> None:
    """Write one notification. Never raises: a failure here must not undo the
    submission or approval it was describing."""
    try:
        await db.notifications.insert_one(to_mongo({
            "id": str(uuid.uuid4()),
            "user_id": recipient_id,
            "kind": kind,                    # submitted | approved | returned
            "message": message,
            "campaign_id": campaign_id,
            "project_name": project_name,
            "actor": actor,
            "read": False,
            "created_at": datetime.now(timezone.utc),
        }))
    except Exception:  # noqa: BLE001
        log.exception("could not write notification for %s", recipient_id)


async def _admin_ids() -> List[dict]:
    return await db.users.find(
        {"role": "admin", "active": True},
        {"_id": 0, "id": 1, "name": 1}).to_list(length=200)


async def _campaign_or_404(campaign_id: str) -> dict:
    doc = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return doc


async def _set_status(campaign_id: str, new_status: str, extra: dict) -> None:
    patch = {"status": new_status, "updated_at": datetime.now(timezone.utc)}
    patch.update(extra)
    await db.campaigns.update_one({"id": campaign_id}, {"$set": to_mongo(patch)})


# ---------------------------------------------------------------------------
# Operator: submit for review
# ---------------------------------------------------------------------------
async def _report_summary(report_id: Optional[str]) -> Optional[dict]:
    if not report_id:
        return None
    doc = await db.report_logs.find_one(
        {"id": report_id},
        {"_id": 0, "id": 1, "version": 1, "filename": 1, "lang": 1,
         "format": 1, "generated_at": 1, "generated_by": 1, "size_bytes": 1})
    return doc


@router.post("/campaigns/{campaign_id}/submit")
async def submit_for_review(campaign_id: str, payload: SubmitPayload,
                            user: dict = Depends(current_user)):
    """Hand the campaign to the reviewing engineer.

    Open to any signed-in account, including admins — a reviewer who prepared
    a campaign themselves may still want it in the queue.
    """
    campaign = await _campaign_or_404(campaign_id)
    if campaign.get("status") == SUBMITTED:
        raise HTTPException(status_code=409,
                            detail="This campaign is already awaiting review")
    # reading_count is computed by the campaigns endpoints at read time and is
    # never stored on the document, so count the readings themselves.
    if not await db.readings.count_documents({"campaign_id": campaign_id}):
        raise HTTPException(
            status_code=422,
            detail="Upload the monitoring data before submitting for review")

    # Pin the exact document under review. Default to the newest version so
    # the ordinary case needs no thought, but record which one it was.
    report = await _report_summary(payload.report_id)
    if payload.report_id and not report:
        raise HTTPException(status_code=404,
                            detail="That report version no longer exists")
    if report is None:
        report = await db.report_logs.find_one(
            {"campaign_id": campaign_id}, {"_id": 0},
            sort=[("generated_at", -1)])
    if not report:
        raise HTTPException(
            status_code=422,
            detail=("Generate the report before submitting it — the reviewer "
                    "needs a document to sign off"))
    if report.get("campaign_id") not in (None, campaign_id):
        raise HTTPException(status_code=422,
                            detail="That report belongs to another campaign")

    now = datetime.now(timezone.utc)
    await _set_status(campaign_id, SUBMITTED, {
        "submitted_by": user["name"],
        "submitted_by_id": user["id"],
        "submitted_at": now,
        "submitted_report_id": report["id"],
        "review_comment": None,
    })

    project = campaign.get("project_name") or "Untitled campaign"
    note = (payload.comment or "").strip()
    vlabel = ("v%03d" % report["version"]) if report.get("version") else "a report"
    message = f"{user['name']} submitted {project} ({vlabel}) for review"
    if note:
        message += f" — {note}"
    admins = await _admin_ids()
    for a in admins:
        if a["id"] != user["id"]:
            await _notify(a["id"], SUBMITTED, message, campaign_id, project,
                          user["name"])

    await audit("campaign.submit", "campaign", campaign_id, user["name"],
                {"comment": note or None, "notified": len(admins),
                 "report_id": report["id"], "version": report.get("version")})
    return {"status": SUBMITTED, "submitted_at": now,
            "report_id": report["id"], "version": report.get("version"),
            "filename": report.get("filename"),
            "notified": len([a for a in admins if a["id"] != user["id"]])}


# ---------------------------------------------------------------------------
# Reviewer: approve / return
# ---------------------------------------------------------------------------
@router.post("/campaigns/{campaign_id}/approve")
async def approve_campaign(campaign_id: str, payload: ReviewNote,
                           user: dict = Depends(require_admin)):
    campaign = await _campaign_or_404(campaign_id)
    now = datetime.now(timezone.utc)
    note = (payload.comment or "").strip()
    await _set_status(campaign_id, APPROVED, {
        "approved_by": user["name"],
        "approved_at": now,
        "review_comment": note or None,
    })

    project = campaign.get("project_name") or "Untitled campaign"
    owner = campaign.get("submitted_by_id")
    if owner and owner != user["id"]:
        message = f"{user['name']} approved {project}"
        if note:
            message += f" — {note}"
        await _notify(owner, APPROVED, message, campaign_id, project,
                      user["name"])

    await audit("campaign.approve", "campaign", campaign_id, user["name"],
                {"comment": note or None})
    return {"status": APPROVED, "approved_at": now}


@router.post("/campaigns/{campaign_id}/return")
async def return_campaign(campaign_id: str, payload: ReviewNote,
                          user: dict = Depends(require_admin)):
    """Send it back to the operator. A comment is required — a rejection with
    no reason means a phone call, which is what this workflow exists to
    avoid."""
    note = (payload.comment or "").strip()
    if not note:
        raise HTTPException(
            status_code=422,
            detail="Say what needs changing — the operator sees this comment")

    campaign = await _campaign_or_404(campaign_id)
    now = datetime.now(timezone.utc)
    await _set_status(campaign_id, READY, {
        "returned_by": user["name"],
        "returned_at": now,
        "review_comment": note,
    })

    project = campaign.get("project_name") or "Untitled campaign"
    owner = campaign.get("submitted_by_id")
    if owner and owner != user["id"]:
        await _notify(owner, "returned",
                      f"{user['name']} returned {project} — {note}",
                      campaign_id, project, user["name"])

    await audit("campaign.return", "campaign", campaign_id, user["name"],
                {"comment": note})
    return {"status": READY, "returned_at": now, "comment": note}


# ---------------------------------------------------------------------------
# The bell
# ---------------------------------------------------------------------------
@router.get("/notifications")
async def list_notifications(limit: int = Query(30, le=100),
                             user: dict = Depends(current_user)):
    docs = await db.notifications.find({"user_id": user["id"]}, {"_id": 0}) \
        .sort("created_at", -1).to_list(length=limit)
    unread = await db.notifications.count_documents(
        {"user_id": user["id"], "read": False})
    return {"unread": unread, "items": docs}


@router.post("/notifications/{notification_id}/read")
async def mark_read(notification_id: str, user: dict = Depends(current_user)):
    await db.notifications.update_one(
        {"id": notification_id, "user_id": user["id"]},
        {"$set": {"read": True}})
    unread = await db.notifications.count_documents(
        {"user_id": user["id"], "read": False})
    return {"unread": unread}


@router.post("/notifications/read-all")
async def mark_all_read(user: dict = Depends(current_user)):
    await db.notifications.update_many(
        {"user_id": user["id"], "read": False}, {"$set": {"read": True}})
    return {"unread": 0}


# ---------------------------------------------------------------------------
# Reviewer's queue — everything waiting, newest first
# ---------------------------------------------------------------------------
@router.get("/review-queue")
async def review_queue(user: dict = Depends(require_admin)):
    """Everything waiting, with the document attached.

    The reviewer should not have to open a campaign, find the Reports tab and
    work out which of seventeen versions is the one being submitted. The
    pinned version travels with the queue entry.
    """
    docs = await db.campaigns.find(
        {"status": SUBMITTED},
        {"_id": 0, "id": 1, "project_name": 1, "client": 1, "site_name": 1,
         "report_number": 1, "revision": 1, "submitted_by": 1,
         "submitted_at": 1, "submitted_report_id": 1, "review_comment": 1}) \
        .sort("submitted_at", -1).to_list(length=200)
    for d in docs:
        d["reading_count"] = await db.readings.count_documents(
            {"campaign_id": d["id"]})
        d["report"] = await _report_summary(d.get("submitted_report_id"))
        # A version generated after submission is not the one under review,
        # but the reviewer should know it exists.
        newest = await db.report_logs.find_one(
            {"campaign_id": d["id"]}, {"_id": 0, "id": 1, "version": 1},
            sort=[("generated_at", -1)])
        d["newer_version_exists"] = bool(
            newest and d.get("submitted_report_id")
            and newest["id"] != d["submitted_report_id"])
    return docs
