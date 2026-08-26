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
# Seed data: KSA ambient air quality standards — Executive Regulation for Air
# Quality (Royal Decree M/165), Appendix 1 for the primary pollutants and
# Appendix 2 for H2S. The allowed exceedance counts are the regulation's own:
# PM10 and PM2.5 are 12 per year, which this table previously carried as 24.
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
     "limit_ugm3": 340, "allowable_exceedances": "12 times per year",
     "allowance": _r(12, AllowanceWindow.ANNUAL, "12 times per year")},
    {"pollutant": "PM10", "averaging_period": "1 Year", "averaging_period_hours": None,
     "limit_ugm3": 50, "allowable_exceedances": "None",
     "allowance": _r(0, AllowanceWindow.ANNUAL_MEAN, "annual arithmetic mean; none allowed")},
    # PM2.5
    {"pollutant": "PM25", "averaging_period": "24 Hour", "averaging_period_hours": 24,
     "limit_ugm3": 35, "allowable_exceedances": "12 times per year",
     "allowance": _r(12, AllowanceWindow.ANNUAL, "12 times per year")},
    {"pollutant": "PM25", "averaging_period": "1 Year", "averaging_period_hours": None,
     "limit_ugm3": 15, "allowable_exceedances": "None",
     "allowance": _r(0, AllowanceWindow.ANNUAL_MEAN, "annual arithmetic mean; none allowed")},
    # Pb — Appendix 1 row 13. A 3-month rolling average with no exceedances
    # allowed. Absent from this table until now, so a campaign measuring lead
    # in TSP had nothing to be judged against.
    {"pollutant": "Pb", "averaging_period": "3 Months", "averaging_period_hours": None,
     "limit_ugm3": 0.15, "allowable_exceedances": "None",
     "allowance": _r(0, AllowanceWindow.ANNUAL_MEAN,
                     "3-month rolling average; none allowed")},
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


# ---------------------------------------------------------------------------
# Soil and water parameter profiles.
#
# Unlike the air and noise limits, the soil and water limit tables are not
# seeded into Mongo at all. They live in soil_water_limits.py, read straight
# from the two Executive Regulations, because a limit table that can be
# edited through the UI is a limit table that can be edited to the wrong
# number — which is precisely how the PM exceedance counts and the
# construction noise standard were wrong for months. The regulation changes
# by decree, not by a user with a keyboard.
#
# What is seeded is the starting set of parameter profiles: the suites BSA
# already runs, so a new campaign is one click rather than ticking forty
# boxes. Profiles are the client's scope of work, not the standard, so they
# are meant to be edited.
# ---------------------------------------------------------------------------
STARTER_PROFILES: List[Dict[str, Any]] = [
    {
        "name": "Soil — TPH, BTEX, metals (standard suite)",
        "medium": "soil",
        "analyte_keys": [
            "f1", "f2", "f3", "f4",
            "benzene", "ethylbenzene", "toluene", "xylene",
            "ph", "phenols", "fluoride", "cyanide_free", "sulphur",
            "as", "cd", "cr", "cu", "pb", "hg", "ni", "zn",
            "ca", "mg", "k",
            "gravel", "sand", "mud",
        ],
    },
    {
        "name": "Soil — full physicochemical and metals",
        "medium": "soil",
        "analyte_keys": [
            "f1", "f2", "f3", "f4",
            "benzene", "ethylbenzene", "toluene", "xylene",
            "fog", "toc", "ph", "conductivity", "phenols",
            "ca", "mg", "k", "fluoride", "cyanide_free", "sulphur",
            "al", "ba", "b", "be", "as", "cd", "cr", "cu", "fe", "mn",
            "co", "pb", "hg", "ni", "ag", "tl", "sn", "v", "zn",
            "chloride", "carbonate", "phosphate", "phosphorus",
            "ammonia_n", "nitrate_n", "tn",
            "gravel", "sand", "mud",
        ],
    },
    {
        "name": "Water — field, chemical and microbiology",
        "medium": "water",
        "analyte_keys": [
            "ph", "temperature", "tds", "do", "conductivity", "salinity",
            "turbidity", "cod", "bod5", "hardness", "alkalinity",
            "chloride", "free_chlorine", "cyanide_free", "fluoride",
            "nitrate_n", "nitrite_n", "phosphate", "sulphate", "sulphide",
            "ammonia_n", "tn", "phosphorus",
            "al", "as", "ba", "cd", "ca", "cr", "co", "cu", "fe", "pb",
            "mg", "mn", "hg", "ni", "se", "na", "zn",
            "benzene", "ethylbenzene", "toluene", "xylene", "phenols",
            "fog", "toc", "tph",
            "ecoli", "intestinal_enterococci", "total_coliform",
        ],
    },
    {
        "name": "Water — metals only",
        "medium": "water",
        "analyte_keys": [
            "al", "sb", "as", "ba", "be", "b", "cd", "ca", "cr", "cr6",
            "co", "cu", "fe", "pb", "li", "mg", "mn", "hg", "mo", "ni",
            "k", "se", "ag", "na", "tl", "sn", "v", "zn",
        ],
    },
    {
        "name": "Sediment — metals, nutrients and organics",
        "medium": "sediment",
        "analyte_keys": [
            "ph", "gravel", "sand", "mud",
            "ba", "cd", "cr", "cr6", "co", "cu", "fe", "pb", "hg", "ni",
            "sn", "zn",
            "phosphate", "phosphorus", "ammonia_n", "nitrate_n", "nitrite_n",
            "tn", "organic_matter", "tph", "pahs",
            "benzene", "ethylbenzene", "toluene", "xylene", "total_vocs",
            "toc",
        ],
    },
]


async def seed_parameter_profiles() -> None:
    """Insert the starter profiles once, then leave them alone.

    `$setOnInsert` only, unlike the limits seed: a profile is a working
    document that BSA is expected to edit, and overwriting an edited profile
    on every redeploy would quietly undo that work.
    """
    from sample_models import ParameterProfile  # local import: avoids a cycle

    created = 0
    for row in STARTER_PROFILES:
        existing = await db.parameter_profiles.find_one(
            {"name": row["name"], "medium": row["medium"]}
        )
        if existing:
            continue
        record = ParameterProfile(**row)
        await db.parameter_profiles.insert_one(to_mongo(record.model_dump()))
        created += 1
    if created:
        log.info("Parameter profiles seeded (%d new).", created)


async def migrate_campaigns() -> None:
    """Idempotent schema repairs to stored campaigns.

    Runs at boot from create_indexes() so the startup hook in server.py does
    not have to change; both are boot-time schema work and both are safe to
    repeat.

    Day period. Article (1) of the Executive Regulation for Noise defines
    daytime as 07:00-20:00. Campaigns created before that was corrected carry
    day_end_hour = 19, which pushes the 19:00-20:00 hour into L Night against
    a limit 10 dB tighter than the one that applies. Changing the model
    default only helps new campaigns, so the stored value is moved here.
    """
    res = await db.campaigns.update_many(
        {"campaign_type": "noise", "day_end_hour": 19},
        {"$set": {"day_end_hour": 20}},
    )
    if res.modified_count:
        log.info("Day period corrected to 07:00-20:00 on %d noise campaign(s);"
                 " their reports need reissuing.", res.modified_count)

    # Soil and water campaigns created before the settings block existed get
    # an empty one. Empty means no standard chosen, which means no verdicts —
    # the correct posture, not a regression.
    res2 = await db.campaigns.update_many(
        {"campaign_type": "soil_water", "sample_settings": {"$exists": False}},
        {"$set": {"sample_settings": {
            "standard": "none",
            "decision_rule": "simple_acceptance",
            "analyte_keys": [],
            "profile_id": None,
            "laboratory": None,
            "lab_accreditation": None,
            "default_context": {},
        }}},
    )
    if res2.modified_count:
        log.info("Sample settings block added to %d soil/water campaign(s).",
                 res2.modified_count)


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
    await db.noise_readings.create_index([("campaign_id", 1), ("timestamp", 1)])
    # The bell reads one user's newest first, and counts their unread.
    await db.notifications.create_index("id", unique=True)
    await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
    await db.notifications.create_index([("user_id", 1), ("read", 1)])
    # Soil and water: laboratory samples belong to a campaign and are read in
    # column order; profiles are looked up by client and medium.
    await db.lab_samples.create_index("id", unique=True)
    await db.lab_samples.create_index([("campaign_id", 1), ("position", 1)])
    await db.lab_samples.create_index([("campaign_id", 1), ("code", 1)], unique=True)
    await db.parameter_profiles.create_index("id", unique=True)
    # Share links are now resolved by their short code on every portal call,
    # so that lookup has to be indexed. Unique, because two live shares with
    # the same code would hand one client another client's reports; sparse,
    # because links issued before the short code existed have no code field
    # and a plain unique index would reject all but the first of them.
    await db.shares.create_index("id", unique=True)
    await db.shares.create_index("code", unique=True, sparse=True)
    await db.shares.create_index([("campaign_id", 1), ("created_at", -1)])
    await db.parameter_profiles.create_index([("medium", 1), ("client", 1)])
    # Client records. The link on a campaign is sparse: every campaign in the
    # archive predates it, and an index that required the field would have
    # nothing to index.
    await db.clients.create_index("id", unique=True)
    await db.clients.create_index("legal_name")
    await db.campaigns.create_index("client_id", sparse=True)
    await migrate_campaigns()
    await seed_parameter_profiles()
