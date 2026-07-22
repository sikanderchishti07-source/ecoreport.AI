"""Pydantic models for EcoReport AI Phase 1 (schema + skeleton).

Datetimes are stored in MongoDB as ISO-8601 strings for reproducibility
(BSON date has ms precision only and tz behavior is client-dependent).
Helpers in db.py convert to/from ISO strings on the storage boundary.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
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
    station_id: Optional[str] = None
    instruments: Optional[List["Instrument"]] = None
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
    station_id: Optional[str] = None
    instruments: List["Instrument"] = Field(default_factory=list)
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
class AllowanceWindow(str, Enum):
    """Governs how the compliance verdict is evaluated for a given limit.

    - SINGLE_EXCEEDANCE: any single exceedance = violation (evaluable from any
      campaign length; e.g. H2S 1h/24h "None allowed").
    - ANNUAL: N allowed exceedances per calendar year (only evaluable when the
      campaign covers >= 75% of the year, i.e. 6570 hours).
    - DAYS_30: N allowed exceedances in any rolling 30-day window (needs >=75%
      of 30 days = 540 hours coverage; e.g. CO 8h "2 in 30 days").
    - ANNUAL_MEAN: the limit IS the annual arithmetic mean (SO2/NO2/PM10/PM25
      1-year limits). Needs >=75% annual data capture to evaluate.
    """
    SINGLE_EXCEEDANCE = "single_exceedance"
    ANNUAL = "annual"
    DAYS_30 = "days_30"
    ANNUAL_MEAN = "annual_mean"


class AllowanceRule(BaseModel):
    """Structured form of 'Number of Allowable Exceedances'."""
    count: Optional[int] = None
    window: AllowanceWindow
    description: str  # human display, e.g. "24 times per year"


class PollutantLimit(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pollutant: str
    averaging_period: str  # human label: "1 Hour" | "8 Hour (rolling)" | "24 Hour" | "1 Year"
    averaging_period_hours: Optional[float] = None  # 1, 8, 24 (None => 1y)
    limit_ugm3: float
    allowable_exceedances: Optional[str] = None  # legacy free-text (display)
    allowance: Optional[AllowanceRule] = None  # NEW structured field
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


# ---------------------------------------------------------------------------
# Phase 2 — Calculation engine output models.
# ---------------------------------------------------------------------------
COMPLIANCE_POLLUTANTS = ("SO2", "NO2", "CO", "H2S", "O3", "PM10", "PM25")
SUPPORTING_POLLUTANTS = ("NO", "NOx")

INSUFFICIENT_STR = "insufficient data \u2014 not reportable"


class PeriodEvaluation(BaseModel):
    """One row per (pollutant × averaging period) — matches BSA report tables."""
    averaging_period: str
    limit_ugm3: float
    allowance_description: str
    # Data-quality gate
    expected_readings: int
    valid_readings: int
    capture_pct: float
    sufficient: bool
    # Statistics (None when sufficient=False)
    max_value: Optional[float] = None
    min_value: Optional[float] = None
    mean_value: Optional[float] = None
    # Exceedance
    exceedance_count: int  # informational — always reported
    exceedance_evaluable: bool
    verdict: str  # "compliant" | "non-compliant" | INSUFFICIENT_STR
    verdict_reason: str


class PollutantEvaluation(BaseModel):
    pollutant: str
    is_supporting: bool  # true for NO, NOx — no compliance verdict
    # Campaign-level hourly capture and stats
    hourly_capture_pct: float
    hourly_valid_count: int
    hourly_expected_count: int
    hourly_max: Optional[float] = None
    hourly_min: Optional[float] = None
    hourly_mean: Optional[float] = None
    # Optional 8-hr rolling stats (populated only for CO and O3)
    rolling_8h_max: Optional[float] = None
    rolling_8h_min: Optional[float] = None
    rolling_8h_mean: Optional[float] = None
    rolling_8h_valid_count: int = 0
    rolling_8h_expected_count: int = 0
    # Per-averaging-period NCEC evaluations (empty for supporting pollutants)
    period_evaluations: List[PeriodEvaluation] = Field(default_factory=list)


class MeteorologySummary(BaseModel):
    monitoring_hours: int
    temp_capture_pct: float
    temp_max: Optional[float] = None
    temp_min: Optional[float] = None
    temp_mean: Optional[float] = None
    rh_capture_pct: float
    rh_max: Optional[float] = None
    rh_min: Optional[float] = None
    rh_mean: Optional[float] = None
    pressure_capture_pct: float
    pressure_max: Optional[float] = None
    pressure_min: Optional[float] = None
    pressure_mean: Optional[float] = None
    wind_speed_capture_pct: float
    wind_speed_max: Optional[float] = None
    wind_speed_min: Optional[float] = None
    wind_speed_mean: Optional[float] = None
    wind_direction_capture_pct: float
    prevailing_wind_direction: Optional[str] = None


class WindDirectionRow(BaseModel):
    direction: str  # "N", "NNE", ...
    counts_by_class: Dict[str, int]
    total: int
    frequency_pct: float


class WindRoseSummary(BaseModel):
    bins: List[WindClassBin]
    direction_rows: List[WindDirectionRow]  # 16 rows (N..NNW)
    class_totals: Dict[str, int]
    class_frequency_pct: Dict[str, float]
    total_valid: int
    total_hours: int
    calms_count: int
    calms_pct: float
    prevailing_direction: Optional[str] = None
    mean_wind_speed: Optional[float] = None


class CampaignSummary(BaseModel):
    campaign_id: str
    monitoring_start: datetime
    monitoring_end: datetime
    monitoring_hours: int
    total_readings: int
    manually_flagged_readings: int
    auto_flagged_readings: int
    overall_hourly_capture_pct: float
    generated_at: datetime = Field(default_factory=utcnow)
    pollutants: List[PollutantEvaluation]
    meteorology: MeteorologySummary
    wind_rose: WindRoseSummary


# ---------------------------------------------------------------------------
# Instruments (Table 4) and mobile-lab library
# ---------------------------------------------------------------------------
class Instrument(BaseModel):
    parameter: str                      # e.g. "SO2" or "NO, NO2, NOX"
    technique: str = ""                 # make / model / EQ reference
    sn: str = ""                        # serial number
    calibration_date: Optional[str] = None


class StationBase(BaseModel):
    """A mobile laboratory: its standard instrument set, saved once and
    loaded into any campaign."""
    name: str                           # e.g. "Mobile Lab 2"
    code: Optional[str] = None          # plate / asset number
    notes: Optional[str] = None
    instruments: List[Instrument] = Field(default_factory=list)


class StationCreate(StationBase):
    pass


class Station(StationBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class StationUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    notes: Optional[str] = None
    instruments: Optional[List[Instrument]] = None


# ---------------------------------------------------------------------------
# Attachments — field photos, calibration certificates, licence, site map
# ---------------------------------------------------------------------------
ATTACHMENT_KINDS = ("site_photo", "calibration", "license", "site_map",
                    "cover_photo")


class Attachment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    campaign_id: str
    kind: str                           # one of ATTACHMENT_KINDS
    filename: str
    path: str
    caption: Optional[str] = None
    instrument_sn: Optional[str] = None  # links a certificate to Table 4
    order: int = 0
    size_bytes: int = 0
    storage: str = "local"
    s3_key: Optional[str] = None
    uploaded_by: str = "system"
    uploaded_at: datetime = Field(default_factory=utcnow)


class AttachmentUpdate(BaseModel):
    caption: Optional[str] = None
    instrument_sn: Optional[str] = None
    order: Optional[int] = None


Campaign.model_rebuild()
CampaignUpdate.model_rebuild()
