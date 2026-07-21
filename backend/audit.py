"""Phase 6 — central audit-trail helper.

Every mutating action in the system records who did what, to which entity,
and when. The acting user is taken from the X-User request header (the
frontend sends the operator name saved in the browser); "system" otherwise.
Audit entries are append-only.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from db import db, to_mongo


async def audit(action: str, entity_type: str, entity_id: str,
                user: str = "system",
                details: Optional[Dict[str, Any]] = None) -> None:
    """Append one audit entry. Never raises — auditing must not break the
    action it describes."""
    try:
        await db.audit_logs.insert_one(to_mongo({
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc),
            "user": (user or "system").strip()[:120] or "system",
            "action": action,                # e.g. campaign.create
            "entity_type": entity_type,      # campaign | readings | reading | report
            "entity_id": entity_id,
            "details": details or {},
        }))
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("audit write failed")


def diff_fields(before: Dict, after: Dict) -> Dict[str, Dict[str, Any]]:
    """Field-level change map {field: {"from": x, "to": y}} for update logs.
    Ignores volatile fields."""
    skip = {"updated_at", "created_at", "reading_count"}
    changes: Dict[str, Dict[str, Any]] = {}
    for k, new in after.items():
        if k in skip:
            continue
        old = before.get(k)
        if old != new:
            changes[k] = {"from": _js(old), "to": _js(new)}
    return changes


def _js(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    return v
