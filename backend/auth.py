"""Phase 7 — authentication core.

Users are stored in the `users` collection with bcrypt password hashes.
Sessions are stateless JWTs (12 h). Set JWT_SECRET in the backend .env for
stable sessions across restarts; without it a random per-boot secret is used
(everyone is logged out on restart) and a warning is logged.

Roles: "admin" (manage users, delete campaigns) and "member" (everything
else). The first account is created through /auth/setup while the users
collection is empty.
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from db import db

log = logging.getLogger(__name__)

JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    JWT_SECRET = secrets.token_hex(32)
    log.warning("JWT_SECRET not set — using a random per-boot secret; "
                "all sessions expire on every server restart. Set JWT_SECRET "
                "in backend/.env for production.")
JWT_ALG = "HS256"
TOKEN_HOURS = 12

_bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user["id"],
        "name": user["name"],
        "role": user["role"],
        "iat": now,
        "exp": now + timedelta(hours=TOKEN_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


async def _user_from_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail="Session expired — please sign in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid session — please sign in")
    user = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0})
    if not user or not user.get("active", True):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail="Account not found or deactivated")
    return user


async def current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail="Not signed in")
    return await _user_from_token(creds.credentials)


async def current_username(user: dict = Depends(current_user)) -> str:
    """Convenience dependency used by the audit trail."""
    return user["name"]


async def require_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="Admin access required")
    return user


def new_user_doc(name: str, username: str, password: str,
                 role: str = "member") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "name": name.strip(),
        "username": username.strip().lower(),
        "password_hash": hash_password(password),
        "role": role,
        "active": True,
        "created_at": datetime.now(timezone.utc),
    }


def public_user(user: dict) -> dict:
    return {k: user.get(k) for k in
            ("id", "name", "username", "role", "active", "created_at")}
