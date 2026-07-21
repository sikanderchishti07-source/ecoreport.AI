"""Pydantic models for EcoReport AI Phase 1 (schema + skeleton).

Datetimes are stored in MongoDB as ISO-8601 strings for reproducibility
(BSON date has ms precision only and tz behavior is client-dependent).
Helpers in db.py convert to/from ISO strings on the storage boundary.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


# ---------------------------------------------------------------------------
# ObjectId helper (kept for future collections that might store BSON _id).
# All primary keys in this app are UUID4 strings on the `id` field.
# ---------------------------------------------------------------------------
def _coerce_object_id(v: Any) -> Any:
    if isinstance(v, ObjectId):
        return str(v)
    return v


PyObjectId = Annotated[str, BeforeValidator(_coerce_object_id)]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Wind-rose speed-class bins (configurable per campaign, defaults specified
# by the client in Phase 0). `max=None` denotes an open-ended upper bound.
# ---------------------------------------------------------------------------
class WindClassBin(BaseModel):
    label: str
    min: float
    max: Optional[float] = None


DEFAULT_WIND_BINS: List[WindClassBin] = [
    WindClassBin(label="Calm", min=0.0, max=2.10),
    WindClassBin(label="2.10-3.60", min=2.10, max=3.60),
    WindClassBin(label="\u22653.60", min=3.60, max=None),
]


# ---------------------------------------------------------------------------
# Campaigns — one monitoring project (site + client + window + metadata).
# ---------------------------------------------------------------------------
class CampaignBase(BaseModel):
    project_name: str
    client: str
    provider: str = "Bander Said Allehiany (BSA)"
    site_name: str
    latitude: float
    longitude: float
    inlet_height_m: float = 5.0
    monitoring_start: datetime
    monitoring_end: datetime
    prepared_by: Optional[str] = None
    project_supervision: Optional[str] = None
    report_number: Optional[str] = None
    revision: str = "00"
    reporting_date: Optional[datetime] = None
    wind_rose_bins: List[WindClassBin] = Field(
        default_factory=lambda: [b.model_copy() for b in DEFAULT_WIND_BINS]
    )


class CampaignCreate(CampaignBase):
    pass


class CampaignUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_name: Optional[str] = None
    client: Optional[str] = None
    provider: Optional[str] = None
    site_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    inlet_height_m: Optional[float] = None
    monitoring_start: Optional[datetime] = None
    monitoring_end: Optional[datetime] = None
    prepared_by: Optional[str] = None
    project_supervision: Optional[str] = None
    report_number: Optional[str] = None
    revision: Optional[str] = None
    reporting_date: Optional[datetime] = None
    wind_rose_bins: Optional[List[WindClassBin]] = None


class Campaign(CampaignBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "draft"  # draft | ingested | ready | archived
    reading_count: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# Readings — one hourly record per timestamp (nullable numeric columns).
# QA flag column is absent from raw files → users flag rows manually via UI.
# ---------------------------------------------------------------------------
POLLUTANT_FIELDS = ("SO2", "NO", "NO2", "NOx", "CO", "H2S", "O3", "PM10", "PM25")
MET_FIELDS = ("Temp", "RH", "Pressure", "WindSpeed", "WindDirection")
ALL_MEASUREMENT_FIELDS = POLLUTANT_FIELDS + MET_FIELDS


class ReadingBase(BaseModel):
    timestamp: datetime
    SO2: Optional[float] = None
    NO: Optional[float] = None
    NO2: Optional[float] = None
    NOx: Optional[float] = None
    CO: Optional[float] = None
    H2S: Optional[float] = None
    O3: Optional[float] = None
    PM10: Optional[float] = None
    PM25: Optional[float] = None
    Temp: Optional[float] = None
    RH: Optional[float] = None
    Pressure: Optional[float] = None
    WindSpeed: Optional[float] = None
    WindDirection: Optional[float] = None


class Reading(ReadingBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    campaign_id: str
    valid: bool = True
    invalidation_reason: Optional[str] = None
    auto_flagged_fields: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class ReadingFlagUpdate(BaseModel):
    valid: bool
    invalidation_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Regulatory reference limits (seeded, read-only in the app).
# ---------------------------------------------------------------------------
class PollutantLimit(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pollutant: str
    averaging_period: str  # human label: "1 Hour" | "8 Hour" | "24 Hour" | "1 Year"
    averaging_period_hours: Optional[float] = None  # 1, 8, 24, 8760 (None => 1y)
    limit_ugm3: float
    allowable_exceedances: Optional[str] = None
    source: str = "KSA NCEC 2020"


# ---------------------------------------------------------------------------
# Upload log — one row per file ingest event.
# ---------------------------------------------------------------------------
class UploadLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    campaign_id: str
    filename: str
    file_type: str  # "csv" | "xlsx" | "xls"
    rows_ingested: int
    rows_skipped: int
    errors: List[str] = Field(default_factory=list)
    recognized_columns: List[str] = Field(default_factory=list)
    ignored_columns: List[str] = Field(default_factory=list)
    # Auto-flagging: negative pollutant values are treated as
    # instrument/calibration errors and their per-field values are nulled.
    auto_flagged_readings: int = 0
    auto_flagged_field_counts: Dict[str, int] = Field(default_factory=dict)
    uploaded_at: datetime = Field(default_factory=utcnow)


class UploadResult(BaseModel):
    upload_log: UploadLog
    preview: List[Reading] = Field(default_factory=list)
