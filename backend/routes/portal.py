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
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import jwt
from fastapi import (APIRouter, Depends, HTTPException, Request, Response,
                     status)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import storage
from audit import audit
from auth import (JWT_ALG, JWT_SECRET, current_user, current_username,
                  require_admin)
from db import db, to_mongo

SHARE_TYP = "share"

# ---------------------------------------------------------------------------
# The link code
#
# A share link used to carry its whole signed token in the URL — around 290
# characters, wrapping across three lines of an email and, being ordinary
# base64, decoding to reveal the campaign's internal identifier to anyone who
# pasted it into a decoder.
#
# The signature was never what authorised the request. Every share is a row in
# this database, and that row is fetched on every call regardless, to check
# revocation and expiry. The signature was a second lock on a door the
# database was already holding shut, at the cost of a link nobody could send
# to a client without apologising for it.
#
# So the URL now carries an opaque code and the row remains the authority.
# Twelve characters drawn from a 32-letter alphabet is 2^60 combinations: at a
# million attempts a second, thirty-six thousand years to find one live link.
#
# The alphabet omits O, 0, I, 1 and L, so a code can be read down a telephone
# or copied off a printed page without the reader having to guess which
# character was meant.
# ---------------------------------------------------------------------------
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 12


def _new_code() -> str:
    """A short, unambiguous, cryptographically random link code."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


async def _unique_code() -> str:
    """A code no live share already holds.

    A collision at this length is vanishingly unlikely, but 'vanishingly
    unlikely' is not 'impossible', and a collision would hand one client
    another client's reports. The check costs one indexed lookup.
    """
    for _ in range(8):
        code = _new_code()
        if not await db.shares.find_one({"code": code}, {"_id": 1}):
            return code
    raise HTTPException(
        status_code=503,
        detail="Could not allocate a link code. Please try again.")

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
                       user: str = Depends(current_username),
                       _admin: dict = Depends(require_admin)):
    """Admin only. A share link downloads the report with no login at all, so
    leaving this open to operators would defeat the download restriction
    entirely."""
    campaign = await db.campaigns.find_one({"id": payload.campaign_id},
                                           {"_id": 0})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    share_id = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(days=payload.days_valid)
    code = await _unique_code()
    doc = {
        "id": share_id,
        "code": code,
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
    # `token` is kept in the response under its original name so the frontend
    # needs no change to keep working; it now holds the short code.
    doc["token"] = code
    doc["code"] = code
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
        # The signed token is never handed back. The short code is: it is not
        # a secret in the way a signature was, it is already in the client's
        # inbox, and being unable to re-copy a link you issued last week
        # meant revoking a working link and sending a second one.
        d.pop("token", None)
    return docs


@router.delete("/shares/{share_id}", status_code=204)
async def revoke_share(share_id: str,
                       user: str = Depends(current_username),
                       _admin: dict = Depends(require_admin)) -> Response:
    doc = await db.shares.find_one({"id": share_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.shares.update_one({"id": share_id}, {"$set": {"revoked": True}})
    await audit("share.revoke", "campaign", doc["campaign_id"], user,
                {"share_id": share_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Public portal (no login)
#
# These are the only endpoints in the application reachable without a session,
# so they are the only ones an outsider can knock on. A short code is far too
# large a space to guess, but an unmetered public endpoint is worth closing on
# its own account: it is also the surface for someone hammering a revoked link
# or scraping for live ones.
#
# The window is generous — a client opening a report, downloading two versions
# and refreshing is nowhere near it — and is keyed on the caller's address
# rather than on the code, so trying many codes from one place is what gets
# stopped.
# ---------------------------------------------------------------------------
PORTAL_MAX_ATTEMPTS = 60
PORTAL_WINDOW_SECONDS = 300
_portal_hits: Dict[str, List[float]] = {}


def _rate_limit(request: Request) -> None:
    """Throttle unauthenticated portal traffic by caller address."""
    client = request.client.host if request.client else "unknown"
    # Behind Render's proxy the peer address is the proxy, so the forwarded
    # header is used when present. It is client-supplied and therefore not
    # trusted for anything but bucketing.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client = forwarded.split(",")[0].strip() or client

    now = time.monotonic()
    cutoff = now - PORTAL_WINDOW_SECONDS
    hits = [t for t in _portal_hits.get(client, []) if t > cutoff]
    if len(hits) >= PORTAL_MAX_ATTEMPTS:
        _portal_hits[client] = hits
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait a few minutes and try "
                   "again.")
    hits.append(now)
    _portal_hits[client] = hits

    # Addresses that have gone quiet are dropped, so a long-running process
    # does not accumulate a bucket per visitor for the life of the container.
    if len(_portal_hits) > 2048:
        for key in [k for k, v in _portal_hits.items()
                    if not any(t > cutoff for t in v)]:
            _portal_hits.pop(key, None)


# ---------------------------------------------------------------------------
def _expiry_of(doc: dict) -> Optional[datetime]:
    """The share's expiry as an aware datetime, however it was stored."""
    exp = doc.get("expires_at")
    if isinstance(exp, str):
        try:
            exp = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(exp, datetime) and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp if isinstance(exp, datetime) else None


def _check(doc: Optional[dict]) -> dict:
    """Apply revocation and expiry to a share row.

    With the signature gone, expiry is enforced here rather than by the token
    library. It has to be: an expiry that lived only inside a token would
    simply stop being checked.
    """
    if not doc:
        raise HTTPException(status_code=404, detail="This link is not valid.")
    if doc.get("revoked"):
        raise HTTPException(status_code=410,
                            detail="This link has been withdrawn.")
    exp = _expiry_of(doc)
    if exp and exp < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=410,
            detail="This link has expired. Please ask for a new one.")
    return doc


async def _resolve(token: str) -> dict:
    """Resolve a share link, by short code or by legacy signed token.

    Links already sent to clients carry the old signed token, and those must
    keep working — a client holding a live link should not find it dead
    because the scheme changed behind them. The short code is tried first
    because every new link uses it; the token path stays for the ones already
    in the world.
    """
    # A short code is fixed-length and drawn from a known alphabet, so it can
    # be told apart from a signed token without guessing.
    if (len(token) == CODE_LENGTH
            and all(c in CODE_ALPHABET for c in token)):
        return _check(await db.shares.find_one({"code": token}, {"_id": 0}))

    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=410,
                            detail="This link has expired. Please ask for a new one.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=404, detail="This link is not valid.")
    if claims.get("typ") != SHARE_TYP:
        raise HTTPException(status_code=404, detail="This link is not valid.")
    doc = _check(await db.shares.find_one({"id": claims.get("sid")},
                                          {"_id": 0}))
    if doc["campaign_id"] != claims.get("cid"):
        raise HTTPException(status_code=404, detail="This link is not valid.")
    return doc


@public.get("/{token}")
async def portal_view(token: str, request: Request,
                      _rl: None = Depends(_rate_limit)):
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
            # Falls back only where a campaign somehow has no provider at
            # all; every real one carries the name it was issued under.
            "name": campaign.get("provider") or "Biological System Analysis (BSA)",
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
async def portal_download(token: str, report_id: str, request: Request,
                          _rl: None = Depends(_rate_limit)):
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
    # The readable name where the record carries one. Reports generated
    # before this existed have only the stored name, so that is the
    # fallback and nothing in the archive becomes undownloadable.
    return FileResponse(path, media_type=media,
                        filename=doc.get("download_name") or doc["filename"])


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
