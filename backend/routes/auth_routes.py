"""Phase 7 — authentication & user-management endpoints.

/auth/status  -> {setup_required} so the frontend knows to show first-run setup
/auth/setup   -> create the first admin account (only while no users exist)
/auth/login   -> {token, user}
/auth/me      -> current user
/auth/users   -> admin: list / create / update / deactivate users

Sign-in is throttled: five failures against a username locks it for fifteen
minutes, and every failure is written to the audit trail. The messages
deliberately never distinguish a wrong password from an unknown username —
saying which was wrong halves the work of guessing the pair.
"""
from __future__ import annotations

import math
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from audit import audit
from auth import (LOCKOUT_MINUTES, MAX_FAILED_ATTEMPTS, burn_password_time,
                  clear_failed_attempts, create_token, current_user,
                  hash_password, lockout_seconds_remaining, new_user_doc,
                  public_user, record_failed_attempt, require_admin,
                  verify_password)
from db import db, to_mongo

router = APIRouter(prefix="/auth", tags=["auth"])

# Shown for every failed sign-in, whatever actually went wrong.
BAD_CREDENTIALS = "Incorrect username or password"


class SetupPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    username: str = Field(min_length=3, max_length=60)
    password: str = Field(min_length=8, max_length=200)


class LoginPayload(BaseModel):
    username: str
    password: str


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
    return (f"Too many failed sign-in attempts. Try again in "
            f"{minutes} {unit}.")


@router.get("/status")
async def auth_status():
    n = await db.users.count_documents({})
    return {"setup_required": n == 0}


@router.post("/setup", status_code=status.HTTP_201_CREATED)
async def first_time_setup(payload: SetupPayload):
    if await db.users.count_documents({}) > 0:
        raise HTTPException(status_code=409,
                            detail="Setup already completed — please sign in")
    user = new_user_doc(payload.name, payload.username, payload.password,
                        role="admin")
    await db.users.insert_one(to_mongo(dict(user)))
    await audit("user.create", "user", user["id"], user["name"],
                {"username": user["username"], "role": "admin",
                 "first_setup": True})
    return {"token": create_token(user), "user": public_user(user)}


@router.post("/login")
async def login(payload: LoginPayload, request: Request):
    username = payload.username.strip().lower()
    ip = _client_ip(request)

    # A locked name is refused before the password is even looked at, so a
    # lockout cannot be worked around by continuing to guess.
    locked = await lockout_seconds_remaining(username)
    if locked > 0:
        raise HTTPException(
            status_code=429,
            detail=_lockout_detail(locked),
            headers={"Retry-After": str(locked)},
        )

    user = await db.users.find_one({"username": username}, {"_id": 0})

    if not user:
        # spend the time a real check would, then count it like any other
        burn_password_time()
        count, locked_seconds = await record_failed_attempt(username, ip)
        await audit("auth.login_failed", "auth", username, username,
                    {"reason": "unknown username", "attempt": count, "ip": ip})
        if locked_seconds:
            await audit("auth.login_locked", "auth", username, username,
                        {"minutes": LOCKOUT_MINUTES, "ip": ip})
            raise HTTPException(
                status_code=429, detail=_lockout_detail(locked_seconds),
                headers={"Retry-After": str(locked_seconds)})
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
            raise HTTPException(
                status_code=429, detail=_lockout_detail(locked_seconds),
                headers={"Retry-After": str(locked_seconds)})
        raise HTTPException(status_code=401, detail=BAD_CREDENTIALS)

    if not user.get("active", True):
        # Counted as well: a deactivated account is still a name someone can
        # sit and guess against.
        await record_failed_attempt(username, ip)
        await audit("auth.login_failed", "auth", user["id"], user["name"],
                    {"reason": "account deactivated", "username": username,
                     "ip": ip})
        raise HTTPException(status_code=403, detail="Account is deactivated")

    await clear_failed_attempts(username)
    await audit("auth.login", "auth", user["id"], user["name"],
                {"username": username, "ip": ip})
    return {"token": create_token(user), "user": public_user(user)}


@router.get("/me")
async def me(user: dict = Depends(current_user)):
    return public_user(user)


@router.get("/users")
async def list_users(_: dict = Depends(require_admin)) -> List[dict]:
    docs = await db.users.find({}, {"_id": 0, "password_hash": 0}) \
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

    Someone who mistypes their password five times should not have to wait a
    quarter of an hour when an admin is standing next to them.
    """
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await clear_failed_attempts(user.get("username", ""))
    await audit("auth.unlock", "user", user_id, admin["name"],
                {"username": user.get("username")})
    return {"unlocked": True, "username": user.get("username")}


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
    fresh = await db.users.find_one({"id": user_id},
                                    {"_id": 0, "password_hash": 0})
    return fresh
