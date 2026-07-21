"""MongoDB connection + serialization helpers + seed data."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from models import PollutantLimit

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
# ---------------------------------------------------------------------------
NCEC_LIMITS: List[Dict[str, Any]] = [
    # SO2
    {"pollutant": "SO2", "averaging_period": "1 Hour", "averaging_period_hours": 1,
     "limit_ugm3": 441, "allowable_exceedances": "24 times per year"},
    {"pollutant": "SO2", "averaging_period": "24 Hour", "averaging_period_hours": 24,
     "limit_ugm3": 217, "allowable_exceedances": "3 times per annum"},
    {"pollutant": "SO2", "averaging_period": "1 Year", "averaging_period_hours": None,
     "limit_ugm3": 65, "allowable_exceedances": "None"},
    # CO
    {"pollutant": "CO", "averaging_period": "1 Hour", "averaging_period_hours": 1,
     "limit_ugm3": 40000, "allowable_exceedances": "1 time per annum"},
    {"pollutant": "CO", "averaging_period": "8 Hour (rolling)", "averaging_period_hours": 8,
     "limit_ugm3": 10000, "allowable_exceedances": "2 times in 30 days"},
    # O3
    {"pollutant": "O3", "averaging_period": "8 Hour (rolling)", "averaging_period_hours": 8,
     "limit_ugm3": 157, "allowable_exceedances": "25 times per annum"},
    # H2S
    {"pollutant": "H2S", "averaging_period": "1 Hour", "averaging_period_hours": 1,
     "limit_ugm3": 14, "allowable_exceedances": "None"},
    {"pollutant": "H2S", "averaging_period": "24 Hour", "averaging_period_hours": 24,
     "limit_ugm3": 4, "allowable_exceedances": "None"},
    # NO2
    {"pollutant": "NO2", "averaging_period": "1 Hour", "averaging_period_hours": 1,
     "limit_ugm3": 200, "allowable_exceedances": "24 times per year"},
    {"pollutant": "NO2", "averaging_period": "1 Year", "averaging_period_hours": None,
     "limit_ugm3": 100, "allowable_exceedances": "None"},
    # PM10
    {"pollutant": "PM10", "averaging_period": "24 Hour", "averaging_period_hours": 24,
     "limit_ugm3": 340, "allowable_exceedances": "24 times per year"},
    {"pollutant": "PM10", "averaging_period": "1 Year", "averaging_period_hours": None,
     "limit_ugm3": 50, "allowable_exceedances": "None"},
    # PM2.5
    {"pollutant": "PM25", "averaging_period": "24 Hour", "averaging_period_hours": 24,
     "limit_ugm3": 35, "allowable_exceedances": "24 times per year"},
    {"pollutant": "PM25", "averaging_period": "1 Year", "averaging_period_hours": None,
     "limit_ugm3": 15, "allowable_exceedances": "None"},
]


async def seed_pollutant_limits() -> None:
    """Idempotent seed. Uses (pollutant, averaging_period) as natural key."""
    for row in NCEC_LIMITS:
        existing = await db.pollutant_limits.find_one(
            {"pollutant": row["pollutant"], "averaging_period": row["averaging_period"]}
        )
        if existing:
            continue
        record = PollutantLimit(**row, source="KSA NCEC 2020")
        await db.pollutant_limits.insert_one(to_mongo(record.model_dump()))
    log.info("NCEC limits seed complete.")


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
