"""Phase 7 — authentication core.

Users are stored in the `users` collection with bcrypt password hashes.
Sessions are stateless JWTs (12 h). Set JWT_SECRET in the backend .env for
stable sessions across restarts; without it a random per-boot secret is used
(everyone is logged out on restart) and a warning is logged.

Roles: "admin" (manage users, delete campaigns) and "member" (everything
else). The first account is created through /auth/setup while the users
collection is empty.

Failed sign-ins are counted per username in `login_attempts` and the name is
locked for a period once the limit is reached. Without this a password can be
guessed as fast as the network allows, which is a larger hole than the absence
of a second factor.
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

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

# ---------------------------------------------------------------------------
# Sign-in throttling
# ---------------------------------------------------------------------------
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

# Counting resets once this long has passed since the last failure, so a
# mistyped password on Monday does not add to one on Friday.
ATTEMPT_WINDOW_MINUTES = 15

# A real bcrypt hash of a value nobody holds. When the username does not
# exist we verify against this instead of returning immediately: bcrypt takes
# a measurable time, so an early return would let someone time the response
# and learn which usernames are real.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode()

_bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def burn_password_time() -> None:
    """Spend the same time a real check would, for an unknown username."""
    verify_password("not-a-real-password", _DUMMY_HASH)


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


# ---------------------------------------------------------------------------
# Failed-attempt tracking
#
# Kept against the username string rather than the user record, so an attempt
# on a name that does not exist is counted too. Counting only real accounts
# would let someone probe for valid usernames without ever being throttled.
# ---------------------------------------------------------------------------
def _as_dt(value) -> Optional[datetime]:
    """Read a stored timestamp back as an aware datetime.

    db.to_mongo writes datetimes as ISO-8601 strings, so what comes back is a
    string on a fresh read and a datetime if the driver has already coerced
    it. Accept either rather than assuming.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def lockout_seconds_remaining(username: str) -> int:
    """Seconds left on a lock, or 0 when the name is not locked."""
    key = (username or "").strip().lower()
    if not key:
        return 0
    rec = await db.login_attempts.find_one({"username": key}, {"_id": 0})
    if not rec:
        return 0
    until = _as_dt(rec.get("locked_until"))
    if not until:
        return 0
    remaining = (until - datetime.now(timezone.utc)).total_seconds()
    return int(remaining) if remaining > 0 else 0


async def record_failed_attempt(username: str,
                                ip: Optional[str] = None) -> Tuple[int, int]:
    """Count one failure. Returns (attempts_used, seconds_locked).

    seconds_locked is 0 unless this failure tripped the limit.
    """
    key = (username or "").strip().lower()
    now = datetime.now(timezone.utc)
    rec = await db.login_attempts.find_one({"username": key}, {"_id": 0})

    count = 0
    if rec:
        last = _as_dt(rec.get("last_failed_at"))
        # a failure long ago is not evidence about this one
        if last and (now - last) <= timedelta(minutes=ATTEMPT_WINDOW_MINUTES):
            count = int(rec.get("count", 0))

    count += 1
    doc = {
        "username": key,
        "count": count,
        "last_failed_at": now.isoformat(),
        "last_ip": ip or "",
    }

    locked_seconds = 0
    if count >= MAX_FAILED_ATTEMPTS:
        until = now + timedelta(minutes=LOCKOUT_MINUTES)
        doc["locked_until"] = until.isoformat()
        locked_seconds = LOCKOUT_MINUTES * 60
    else:
        doc["locked_until"] = None

    await db.login_attempts.update_one({"username": key}, {"$set": doc},
                                       upsert=True)
    return count, locked_seconds


async def clear_failed_attempts(username: str) -> None:
    """Wipe the record after a successful sign-in."""
    key = (username or "").strip().lower()
    if key:
        await db.login_attempts.delete_one({"username": key})
