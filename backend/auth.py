"""Phase 7 — authentication core.

Users are stored in the `users` collection with bcrypt password hashes.
Sessions are stateless JWTs (12 h). Set JWT_SECRET in the backend .env for
stable sessions across restarts; without it a random per-boot secret is used
(everyone is logged out on restart) and a warning is logged.

Roles: "admin" (manage users, delete campaigns) and "member" (everything
else). The first account is created through /auth/setup while the users
collection is empty.

Sign-in is in two steps. The password buys a short-lived challenge token,
good only for proving a six-digit TOTP code; the session token is issued
after that. Failed passwords AND failed codes are counted per username in
`login_attempts` and the name is locked once the limit is reached — six
digits is a million combinations, which is guessable in minutes if nothing
throttles it.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import bcrypt
import jwt
import pyotp
import qrcode
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

# The password step buys only this long to produce a code. Long enough to
# find the phone, short enough that a stolen challenge is worthless.
CHALLENGE_MINUTES = 5

# What the authenticator app shows above the code.
TOTP_ISSUER = "EcoReport AI"

# Codes are accepted one step either side of now, so a phone whose clock is
# half a minute out still works.
TOTP_VALID_WINDOW = 1
TOTP_PERIOD = 30

RECOVERY_CODE_COUNT = 8

# ---------------------------------------------------------------------------
# Sign-in throttling
# ---------------------------------------------------------------------------
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
ATTEMPT_WINDOW_MINUTES = 15

# A real bcrypt hash of a value nobody holds. When the username does not
# exist we verify against this instead of returning immediately: bcrypt takes
# a measurable time, so an early return would let someone time the response
# and learn which usernames are real.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode()

# Fields that must never leave the server.
SECRET_FIELDS = {"password_hash": 0, "totp_secret": 0,
                 "totp_pending_secret": 0, "recovery_code_hashes": 0}

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


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------
def create_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user["id"],
        "name": user["name"],
        "role": user["role"],
        "typ": "session",
        "iat": now,
        "exp": now + timedelta(hours=TOKEN_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def create_challenge_token(user: dict) -> str:
    """Proof that the password was right — and nothing else.

    Marked with its own type so it can never be presented as a session: a
    half-finished sign-in must not reach any campaign data.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user["id"],
        "typ": "2fa",
        "iat": now,
        "exp": now + timedelta(minutes=CHALLENGE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


async def user_from_challenge(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail="That took too long — please sign in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid sign-in attempt — please start again")
    if payload.get("typ") != "2fa":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid sign-in attempt — please start again")
    user = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0})
    if not user or not user.get("active", True):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail="Account not found or deactivated")
    return user


async def _user_from_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail="Session expired — please sign in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid session — please sign in")
    # a challenge token is not a session, however valid its signature
    if payload.get("typ") == "2fa":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail="Sign-in not completed — please sign in")
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
        # every account enrols in two-factor at its first sign-in
        "totp_enabled": False,
        "totp_secret": None,
        "totp_pending_secret": None,
        "totp_last_step": 0,
        "recovery_code_hashes": [],
        "created_at": datetime.now(timezone.utc),
    }


def public_user(user: dict) -> dict:
    return {k: user.get(k) for k in
            ("id", "name", "username", "role", "active", "created_at")} | {
        "totp_enabled": bool(user.get("totp_enabled")),
    }


# ---------------------------------------------------------------------------
# TOTP
# ---------------------------------------------------------------------------
def new_totp_secret() -> str:
    return pyotp.random_base32()


def otpauth_uri(secret: str, username: str) -> str:
    """The string the QR code encodes."""
    return pyotp.TOTP(secret, interval=TOTP_PERIOD).provisioning_uri(
        name=username, issuer_name=TOTP_ISSUER)


def qr_data_uri(uri: str) -> str:
    """Render the otpauth URI as a PNG the browser can show inline.

    Returned as a data URI rather than a file so the secret never touches
    disk and no extra route has to be protected.
    """
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def verify_totp(secret: str, code: str,
                last_step: int = 0) -> Tuple[bool, int]:
    """Check a six-digit code and return (ok, the step it belonged to).

    The step is returned so the caller can store it and refuse the same code
    twice. Without that, a code shouted across a room — or read off a
    shoulder — stays usable for the rest of its thirty seconds.
    """
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6 or not secret:
        return False, 0
    totp = pyotp.TOTP(secret, interval=TOTP_PERIOD)
    now_step = int(time.time()) // TOTP_PERIOD
    for step in range(now_step - TOTP_VALID_WINDOW,
                      now_step + TOTP_VALID_WINDOW + 1):
        if secrets.compare_digest(totp.at(step * TOTP_PERIOD), code):
            if step <= int(last_step or 0):
                return False, step          # already spent
            return True, step
    return False, 0


# ---------------------------------------------------------------------------
# Recovery codes
# ---------------------------------------------------------------------------
def generate_recovery_codes(n: int = RECOVERY_CODE_COUNT) -> List[str]:
    """Human-copyable one-time codes, e.g. 'K7QD-2M4X'.

    The alphabet omits I, O, 0 and 1 — these get written on paper and read
    back later, and those four are what people mistype.
    """
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    out = []
    for _ in range(n):
        raw = "".join(secrets.choice(alphabet) for _ in range(8))
        out.append(f"{raw[:4]}-{raw[4:]}")
    return out


def hash_recovery_codes(codes: List[str]) -> List[str]:
    return [hash_password(_normalise_recovery(c)) for c in codes]


def _normalise_recovery(code: str) -> str:
    return (code or "").strip().upper().replace(" ", "").replace("-", "")


def consume_recovery_code(code: str, hashes: List[str]) -> Optional[int]:
    """Index of the hash this code matches, or None.

    The caller removes that entry: a recovery code works exactly once.
    """
    candidate = _normalise_recovery(code)
    if not candidate:
        return None
    for i, h in enumerate(hashes or []):
        if verify_password(candidate, h):
            return i
    return None


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
