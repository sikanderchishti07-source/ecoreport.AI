"""Phase 7 — authentication & user-management endpoints.

/auth/status  -> {setup_required} so the frontend knows to show first-run setup
/auth/setup   -> create the first admin account (only while no users exist)
/auth/login   -> {token, user}
/auth/me      -> current user
/auth/users   -> admin: list / create / update / deactivate users
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from audit import audit
from auth import (create_token, current_user, hash_password, new_user_doc,
                  public_user, require_admin, verify_password)
from db import db, to_mongo

router = APIRouter(prefix="/auth", tags=["auth"])


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
async def login(payload: LoginPayload):
    user = await db.users.find_one(
        {"username": payload.username.strip().lower()}, {"_id": 0})
    if not user or not verify_password(payload.password,
                                       user.get("password_hash", "")):
        raise HTTPException(status_code=401,
                            detail="Incorrect username or password")
    if not user.get("active", True):
        raise HTTPException(status_code=403, detail="Account is deactivated")
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
    fresh = await db.users.find_one({"id": user_id},
                                    {"_id": 0, "password_hash": 0})
    return fresh
