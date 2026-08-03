"""Phase 7 — authentication & user-management endpoints.

/auth/status        -> {setup_required}
/auth/setup         -> create the first admin account (only while none exist)
/auth/login         -> password step; returns a challenge, never a session
/auth/login/verify  -> code step; returns {token, user}
/auth/me            -> current user
/auth/users         -> admin: list / create / update / deactivate / reset 2FA

Sign-in is two steps. The password returns a challenge token good for five
minutes and nothing else; the session is issued only once a six-digit code is
proved. Every failure — wrong password, wrong code, unknown username — counts
towards the same limit, and five of them lock the name for fifteen minutes.

Messages never distinguish a wrong password from an unknown username. Saying
which was wrong halves the work of guessing the pair.
"""
from __future__ import annotations

import math
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from audit import audit
from auth import (LOCKOUT_MINUTES, SECRET_FIELDS, burn_password_time,
                  clear_failed_attempts, consume_recovery_code,
                  create_challenge_token, create_token, current_user,
                  generate_recovery_codes, hash_password,
                  hash_recovery_codes, lockout_seconds_remaining,
                  new_totp_secret, new_user_doc, otpauth_uri, public_user,
                  qr_data_uri, record_failed_attempt, require_admin,
                  user_from_challenge, verify_password, verify_totp)
from db import db, to_mongo

router = APIRouter(prefix="/auth", tags=["auth"])

BAD_CREDENTIALS = "Incorrect username or password"
BAD_CODE = "That code is not right. Check the app and try again."


class SetupPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    username: str = Field(min_length=3, max_length=60)
    password: str = Field(min_length=8, max_length=200)


class LoginPayload(BaseModel):
    username: str
    password: str


class VerifyPayload(BaseModel):
    challenge: str
    code: str = Field(min_length=4, max_length=20)


class CreateUserPayload(SetupPayload):
    role: str = Field(default="member", pattern="^(admin|member)$")


class UpdateUserPayload(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    role: Optional[str] = Field(default=None, pattern="^(admin|member)$")
    active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=200)


def _client_ip(request: Request) -> str:
    """Best available caller address.

    Render sits behind a proxy, so the socket address is the proxy's. The
    first entry of X-Forwarded-For is the original caller. It is caller-
    supplied and therefore not trustworthy for access decisions — it is
    recorded for the audit trail only, never used to allow or deny.
    """
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def _lockout_detail(seconds: int) -> str:
    minutes = max(1, math.ceil(seconds / 60))
    unit = "minute" if minutes == 1 else "minutes"
    return f"Too many failed sign-in attempts. Try again in {minutes} {unit}."


def _locked_error(seconds: int) -> HTTPException:
    return HTTPException(status_code=429, detail=_lockout_detail(seconds),
                         headers={"Retry-After": str(seconds)})


@router.get("/status")
async def auth_status():
    n = await db.users.count_documents({})
    return {"setup_required": n == 0}


@router.post("/setup", status_code=status.HTTP_201_CREATED)
async def first_time_setup(payload: SetupPayload):
    """Create the first admin.

    Returns a challenge rather than a session: the very first account enrols
    in two-factor immediately, like every other one.
    """
    if await db.users.count_documents({}) > 0:
        raise HTTPException(status_code=409,
                            detail="Setup already completed — please sign in")
    user = new_user_doc(payload.name, payload.username, payload.password,
                        role="admin")
    secret = new_totp_secret()
    user["totp_pending_secret"] = secret
    await db.users.insert_one(to_mongo(dict(user)))
    await audit("user.create", "user", user["id"], user["name"],
                {"username": user["username"], "role": "admin",
                 "first_setup": True})
    uri = otpauth_uri(secret, user["username"])
    return {
        "stage": "enroll",
        "challenge": create_challenge_token(user),
        "qr": qr_data_uri(uri),
        "secret": secret,
        "name": user["name"],
    }


@router.post("/login")
async def login(payload: LoginPayload, request: Request):
    username = payload.username.strip().lower()
    ip = _client_ip(request)

    # A locked name is refused before the password is even looked at, so a
    # lockout cannot be worked around by continuing to guess.
    locked = await lockout_seconds_remaining(username)
    if locked > 0:
        raise _locked_error(locked)

    user = await db.users.find_one({"username": username}, {"_id": 0})

    if not user:
        burn_password_time()
        count, locked_seconds = await record_failed_attempt(username, ip)
        await audit("auth.login_failed", "auth", username, username,
                    {"reason": "unknown username", "attempt": count, "ip": ip})
        if locked_seconds:
            await audit("auth.login_locked", "auth", username, username,
                        {"minutes": LOCKOUT_MINUTES, "ip": ip})
            raise _locked_error(locked_seconds)
        raise HTTPException(status_code=401, detail=BAD_CREDENTIALS)

    if not verify_password(payload.password, user.get("password_hash", "")):
        count, locked_seconds = await record_failed_attempt(username, ip)
        await audit("auth.login_failed", "auth", user["id"], user["name"],
                    {"reason": "wrong password", "username": username,
                     "attempt": count, "ip": ip})
        if locked_seconds:
            await audit("auth.login_locked", "auth", user["id"], user["name"],
                        {"username": username, "minutes": LOCKOUT_MINUTES,
                         "ip": ip})
            raise _locked_error(locked_seconds)
        raise HTTPException(status_code=401, detail=BAD_CREDENTIALS)

    if not user.get("active", True):
        await record_failed_attempt(username, ip)
        await audit("auth.login_failed", "auth", user["id"], user["name"],
                    {"reason": "account deactivated", "username": username,
                     "ip": ip})
        raise HTTPException(status_code=403, detail="Account is deactivated")

    # Password proved. Nothing else is granted yet.
    if user.get("totp_enabled") and user.get("totp_secret"):
        return {"stage": "totp", "challenge": create_challenge_token(user),
                "name": user["name"]}

    # Not enrolled — issue a fresh secret every time this screen is reached,
    # so an abandoned enrolment leaves nothing usable behind.
    secret = new_totp_secret()
    await db.users.update_one({"id": user["id"]},
                              {"$set": {"totp_pending_secret": secret}})
    uri = otpauth_uri(secret, user["username"])
    return {
        "stage": "enroll",
        "challenge": create_challenge_token(user),
        "qr": qr_data_uri(uri),
        "secret": secret,
        "name": user["name"],
    }


@router.post("/login/verify")
async def login_verify(payload: VerifyPayload, request: Request):
    """Second step: prove a six-digit code, or spend a recovery code."""
    user = await user_from_challenge(payload.challenge)
    username = user.get("username", "")
    ip = _client_ip(request)

    locked = await lockout_seconds_remaining(username)
    if locked > 0:
        raise _locked_error(locked)

    async def _fail(reason: str, detail: str):
        count, locked_seconds = await record_failed_attempt(username, ip)
        await audit("auth.2fa_failed", "auth", user["id"], user["name"],
                    {"reason": reason, "username": username,
                     "attempt": count, "ip": ip})
        if locked_seconds:
            await audit("auth.login_locked", "auth", user["id"], user["name"],
                        {"username": username, "minutes": LOCKOUT_MINUTES,
                         "ip": ip})
            raise _locked_error(locked_seconds)
        raise HTTPException(status_code=401, detail=detail)

    # ---- enrolment ------------------------------------------------------
    if not user.get("totp_enabled"):
        secret = user.get("totp_pending_secret")
        if not secret:
            raise HTTPException(status_code=409,
                                detail="Setup expired — please sign in again")
        ok, step = verify_totp(secret, payload.code,
                               last_step=user.get("totp_last_step", 0))
        if not ok:
            await _fail("enrolment code wrong", BAD_CODE)

        codes = generate_recovery_codes()
        await db.users.update_one({"id": user["id"]}, {"$set": {
            "totp_enabled": True,
            "totp_secret": secret,
            "totp_pending_secret": None,
            "totp_last_step": step,
            "recovery_code_hashes": hash_recovery_codes(codes),
        }})
        await clear_failed_attempts(username)
        await audit("auth.2fa_enrolled", "user", user["id"], user["name"],
                    {"username": username, "ip": ip})
        fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
        return {
            "token": create_token(fresh),
            "user": public_user(fresh),
            # shown once and never again — the only copy is the one the
            # person writes down on this screen
            "recovery_codes": codes,
        }

    # ---- normal sign-in --------------------------------------------------
    ok, step = verify_totp(user.get("totp_secret", ""), payload.code,
                           last_step=user.get("totp_last_step", 0))
    if ok:
        await db.users.update_one({"id": user["id"]},
                                  {"$set": {"totp_last_step": step}})
        await clear_failed_attempts(username)
        await audit("auth.login", "auth", user["id"], user["name"],
                    {"username": username, "method": "totp", "ip": ip})
        return {"token": create_token(user), "user": public_user(user)}

    # a recovery code is the other accepted answer here
    idx = consume_recovery_code(payload.code,
                                user.get("recovery_code_hashes", []))
    if idx is not None:
        remaining = list(user.get("recovery_code_hashes", []))
        remaining.pop(idx)
        await db.users.update_one({"id": user["id"]},
                                  {"$set": {"recovery_code_hashes": remaining}})
        await clear_failed_attempts(username)
        await audit("auth.login", "auth", user["id"], user["name"],
                    {"username": username, "method": "recovery code",
                     "codes_left": len(remaining), "ip": ip})
        return {"token": create_token(user), "user": public_user(user),
                "recovery_codes_remaining": len(remaining)}

    await _fail("wrong code", BAD_CODE)


@router.get("/me")
async def me(user: dict = Depends(current_user)):
    return public_user(user)


@router.get("/users")
async def list_users(_: dict = Depends(require_admin)) -> List[dict]:
    projection = {"_id": 0} | SECRET_FIELDS
    docs = await db.users.find({}, projection) \
        .sort("created_at", 1).to_list(length=500)
    return docs


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(payload: CreateUserPayload,
                      admin: dict = Depends(require_admin)):
    exists = await db.users.find_one(
        {"username": payload.username.strip().lower()})
    if exists:
        raise HTTPException(status_code=409, detail="Username already taken")
    user = new_user_doc(payload.name, payload.username, payload.password,
                        role=payload.role)
    await db.users.insert_one(to_mongo(dict(user)))
    await audit("user.create", "user", user["id"], admin["name"],
                {"username": user["username"], "role": user["role"]})
    return public_user(user)


@router.post("/users/{user_id}/unlock")
async def unlock_user(user_id: str, admin: dict = Depends(require_admin)):
    """Clear a lockout early.

    Someone who mistypes five times should not wait a quarter of an hour when
    an admin is standing next to them.
    """
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await clear_failed_attempts(user.get("username", ""))
    await audit("auth.unlock", "user", user_id, admin["name"],
                {"username": user.get("username")})
    return {"unlocked": True, "username": user.get("username")}


@router.post("/users/{user_id}/reset-2fa")
async def reset_two_factor(user_id: str, admin: dict = Depends(require_admin)):
    """Wipe someone's authenticator setup — the lost-phone path.

    Their next sign-in shows a fresh QR code and issues new recovery codes.
    The old secret and the old codes stop working immediately.
    """
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one({"id": user_id}, {"$set": {
        "totp_enabled": False,
        "totp_secret": None,
        "totp_pending_secret": None,
        "totp_last_step": 0,
        "recovery_code_hashes": [],
    }})
    await clear_failed_attempts(user.get("username", ""))
    await audit("auth.2fa_reset", "user", user_id, admin["name"],
                {"username": user.get("username")})
    return {"reset": True, "username": user.get("username")}


@router.patch("/users/{user_id}")
async def update_user(user_id: str, payload: UpdateUserPayload,
                      admin: dict = Depends(require_admin)):
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    updates: dict = {}
    changes: dict = {}
    if payload.name is not None and payload.name != user["name"]:
        updates["name"] = payload.name.strip()
        changes["name"] = {"from": user["name"], "to": updates["name"]}
    if payload.role is not None and payload.role != user["role"]:
        updates["role"] = payload.role
        changes["role"] = {"from": user["role"], "to": payload.role}
    if payload.active is not None and payload.active != user.get("active", True):
        updates["active"] = payload.active
        changes["active"] = {"from": user.get("active", True),
                             "to": payload.active}
    if payload.password:
        updates["password_hash"] = hash_password(payload.password)
        changes["password"] = {"from": "•••", "to": "reset"}
    # Safety: never let the last active admin lock themselves out
    if (updates.get("role") == "member" or updates.get("active") is False) \
            and user["role"] == "admin":
        n_admins = await db.users.count_documents(
            {"role": "admin", "active": True, "id": {"$ne": user_id}})
        if n_admins == 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot demote or deactivate the last active admin")
    if updates:
        await db.users.update_one({"id": user_id}, {"$set": to_mongo(updates)})
        await audit("user.update", "user", user_id, admin["name"],
                    {"username": user["username"], "changes": changes})
        # A password reset should not leave the person locked out by the
        # attempts that prompted the reset.
        if payload.password:
            await clear_failed_attempts(user.get("username", ""))
    projection = {"_id": 0} | SECRET_FIELDS
    fresh = await db.users.find_one({"id": user_id}, projection)
    return fresh
