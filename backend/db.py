"""MongoDB connection + serialization helpers + seed data."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from models import AllowanceRule, AllowanceWindow, PollutantLimit

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

_client: AsyncIOMotorClient = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = _client[os.environ["DB_NAME"]]

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Datetime <-> ISO string helpers. All datetimes are stored as ISO strings.
# ---------------------------------------------------------------------------
def _walk(value: Any, transform):
    if isinstance(value, dict):
        return {k: _walk(v, transform) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk(v, transform) for v in value]
    return transform(value)


def to_mongo(doc: Dict[str, Any]) -> Dict[str, Any]:
    def _t(v):
        if isinstance(v, datetime):
            return v.isoformat()
        return v

    return _walk(doc, _t)


def from_mongo(doc: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Strip the BSON _id field. Datetimes come back as strings; Pydantic
    will parse them via its native ISO-8601 support."""
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop("_id", None)
    return doc


# ---------------------------------------------------------------------------
# Seed data: KSA NCEC 2020 Ambient Air Quality Standards (Table 5).
# Includes structured `allowance` per Phase 2 Rule B taxonomy.
# ---------------------------------------------------------------------------
def _r(count, window, description):
    return AllowanceRule(count=count, window=window, description=description).model_dump()


NCEC_LIMITS: List[Dict[str, Any]] = [
    # SO2
    {"pollutant": "SO2", "averaging_period": "1 Hour", "averaging_period_hours": 1,
     "limit_ugm3": 441, "allowable_exceedances": "24 times per year",
     "allowance": _r(24, AllowanceWindow.ANNUAL, "24 times per year")},
    {"pollutant": "SO2", "averaging_period": "24 Hour", "averaging_period_hours": 24,
     "limit_ugm3": 217, "allowable_exceedances": "3 times per annum",
     "allowance": _r(3, AllowanceWindow.ANNUAL, "3 times per annum")},
    {"pollutant": "SO2", "averaging_period": "1 Year", "averaging_period_hours": None,
     "limit_ugm3": 65, "allowable_exceedances": "None",
     "allowance": _r(0, AllowanceWindow.ANNUAL_MEAN, "annual arithmetic mean; none allowed")},
    # CO
    {"pollutant": "CO", "averaging_period": "1 Hour", "averaging_period_hours": 1,
     "limit_ugm3": 40000, "allowable_exceedances": "1 time per annum",
     "allowance": _r(1, AllowanceWindow.ANNUAL, "1 time per annum")},
    {"pollutant": "CO", "averaging_period": "8 Hour (rolling)", "averaging_period_hours": 8,
     "limit_ugm3": 10000, "allowable_exceedances": "2 times in 30 days",
     "allowance": _r(2, AllowanceWindow.DAYS_30, "2 times in 30 days")},
    # O3
    {"pollutant": "O3", "averaging_period": "8 Hour (rolling)", "averaging_period_hours": 8,
     "limit_ugm3": 157, "allowable_exceedances": "25 times per annum",
     "allowance": _r(25, AllowanceWindow.ANNUAL, "25 times per annum")},
    # H2S — zero tolerance on both periods
    {"pollutant": "H2S", "averaging_period": "1 Hour", "averaging_period_hours": 1,
     "limit_ugm3": 14, "allowable_exceedances": "None",
     "allowance": _r(0, AllowanceWindow.SINGLE_EXCEEDANCE, "None allowed")},
    {"pollutant": "H2S", "averaging_period": "24 Hour", "averaging_period_hours": 24,
     "limit_ugm3": 4, "allowable_exceedances": "None",
     "allowance": _r(0, AllowanceWindow.SINGLE_EXCEEDANCE, "None allowed")},
    # NO2
    {"pollutant": "NO2", "averaging_period": "1 Hour", "averaging_period_hours": 1,
     "limit_ugm3": 200, "allowable_exceedances": "24 times per year",
     "allowance": _r(24, AllowanceWindow.ANNUAL, "24 times per year")},
    {"pollutant": "NO2", "averaging_period": "1 Year", "averaging_period_hours": None,
     "limit_ugm3": 100, "allowable_exceedances": "None",
     "allowance": _r(0, AllowanceWindow.ANNUAL_MEAN, "annual arithmetic mean; none allowed")},
    # PM10
    {"pollutant": "PM10", "averaging_period": "24 Hour", "averaging_period_hours": 24,
     "limit_ugm3": 340, "allowable_exceedances": "24 times per year",
     "allowance": _r(24, AllowanceWindow.ANNUAL, "24 times per year")},
    {"pollutant": "PM10", "averaging_period": "1 Year", "averaging_period_hours": None,
     "limit_ugm3": 50, "allowable_exceedances": "None",
     "allowance": _r(0, AllowanceWindow.ANNUAL_MEAN, "annual arithmetic mean; none allowed")},
    # PM2.5
    {"pollutant": "PM25", "averaging_period": "24 Hour", "averaging_period_hours": 24,
     "limit_ugm3": 35, "allowable_exceedances": "24 times per year",
     "allowance": _r(24, AllowanceWindow.ANNUAL, "24 times per year")},
    {"pollutant": "PM25", "averaging_period": "1 Year", "averaging_period_hours": None,
     "limit_ugm3": 15, "allowable_exceedances": "None",
     "allowance": _r(0, AllowanceWindow.ANNUAL_MEAN, "annual arithmetic mean; none allowed")},
]


async def seed_pollutant_limits() -> None:
    """Idempotent upsert. (pollutant, averaging_period) is the natural key;
    all other fields are overwritten so existing rows pick up new schema
    additions (like the structured `allowance`) on the next boot."""
    for row in NCEC_LIMITS:
        key = {"pollutant": row["pollutant"], "averaging_period": row["averaging_period"]}
        record = PollutantLimit(**row, source="KSA NCEC 2020")
        doc = to_mongo(record.model_dump())
        set_fields = {k: v for k, v in doc.items() if k != "id"}
        await db.pollutant_limits.update_one(
            key,
            {"$set": set_fields, "$setOnInsert": {"id": doc["id"]}},
            upsert=True,
        )
    log.info("NCEC limits seed complete (%d rows).", len(NCEC_LIMITS))


async def create_indexes() -> None:
    """Create supporting indexes."""
    await db.campaigns.create_index("id", unique=True)
    await db.readings.create_index("id", unique=True)
    await db.readings.create_index([("campaign_id", 1), ("timestamp", 1)])
    await db.pollutant_limits.create_index(
        [("pollutant", 1), ("averaging_period", 1)], unique=True
    )
    await db.upload_logs.create_index("id", unique=True)
    await db.upload_logs.create_index([("campaign_id", 1), ("uploaded_at", -1)])
