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
# Gas units, per gas
#
# An analyser export does not use one unit throughout. The BSA fleet reports
# six gases in ppb and CO in ppm, in the same file, with no units row to say
# so. A single campaign-wide setting cannot describe that: "ppb" leaves CO a
# thousand times too small, "ppm" inflates the other six by the same factor,
# and "ugm3" passes every raw number through unconverted. All three failures
# are silent, and the resulting figures look plausible.
#
# So units are declared per gas. Resolution order on ingest is:
#   1. a units row inside the uploaded file      (locked rule — file wins)
#   2. this per-gas map
#   3. the legacy campaign-wide `gas_units`      (older campaigns)
#
# Campaigns created before this field existed have an empty map and therefore
# keep their previous behaviour exactly.
# ---------------------------------------------------------------------------
GAS_UNIT_FIELDS = ("SO2", "NO", "NO2", "NOx", "O3", "H2S", "CO")

DEFAULT_GAS_UNITS_MAP: Dict[str, str] = {
    "SO2": "ppb",
    "NO": "ppb",
    "NO2": "ppb",
    "NOx": "ppb",
    "O3": "ppb",
    "H2S": "ppb",
    "CO": "ppm",
}


# ---------------------------------------------------------------------------
# Campaigns — one monitoring project (site + client + window + metadata).
# ---------------------------------------------------------------------------
# The four NCEC land-use categories plus roadside, industrial and
# construction, and a deliberate "to be determined" that produces a report
# which states the measured levels against every category without judging —
# the posture BSA's manual noise reports take when the client has not yet
# fixed the category.
NOISE_CATEGORIES = ("A", "B", "C", "D", "roadside", "industrial",
                    "construction", "tbd")

# The zones a construction work site can sit inside. Construction is not a
# zone in its own right, so it cannot be its own base.
CONSTRUCTION_BASE_CATEGORIES = ("A", "B", "C", "D", "roadside", "industrial")


class CampaignBase(BaseModel):
    # "air" is the original ambient-air campaign; "noise" is an attended
    # sound-level survey. The type decides which ingest, engine and report
    # generator a campaign uses — everything else (review workflow,
    # versioning, attachments, the viewer) is shared.
    campaign_type: str = "air"
    project_name: str
    client: str
    provider: str = "Bander Said Allehiany (BSA)"
    site_name: str
    latitude: float
    longitude: float
    inlet_height_m: float = 5.0
    facility_latitude: Optional[float] = None   # optional: the plant/source,
    facility_longitude: Optional[float] = None  # used only to state geometry
    gas_units: str = "ugm3"          # LEGACY campaign-wide fallback:
                                     # "ugm3" | "ppb" | "ppm". Retained so
                                     # existing campaigns are untouched.
    gas_units_map: Dict[str, str] = Field(default_factory=dict)
                                     # per-gas units, e.g. {"CO": "ppm", ...}
                                     # empty => fall back to gas_units
    monitoring_start: datetime
    monitoring_end: datetime
    prepared_by: Optional[str] = None
    project_supervision: Optional[str] = None
    report_number: Optional[str] = None
    revision: str = "00"
    document_status: str = "Issued for Client Use"
    reporting_date: Optional[datetime] = None
    wind_rose_bins: List[WindClassBin] = Field(
        default_factory=lambda: [b.model_copy() for b in DEFAULT_WIND_BINS]
    )
    # --- noise campaigns only -------------------------------------------
    noise_category: str = "tbd"        # one of NOISE_CATEGORIES
    # Article (1) of the Executive Regulation for Noise defines daytime as
    # 07:00-20:00 and night-time as 20:00-07:00. The default was 19 and put
    # the 19:00-20:00 hour into the night average, where the limit is 10 dB
    # tighter. The field stays editable for the rare job that is measured to
    # a different agreed window, but 20 is the regulation.
    day_start_hour: int = 7
    day_end_hour: int = 20
    # Article (7): a construction work site has no standard of its own. It
    # takes the standard of the zone around it, corrected by the Table (4)
    # value for the duration of activities, and only between 07:00 and 18:00.
    # Both facts are needed before any verdict can be given; left blank, the
    # report states the levels and makes no judgement.
    construction_base_category: Optional[str] = None   # A|B|C|D|roadside|
                                                       # industrial
    construction_hours_per_day: Optional[float] = None # duration of activity
    meter_model: Optional[str] = None  # sound level meter, printed in
    meter_serial: Optional[str] = None # the methodology section
    calibrator_model: Optional[str] = None
    calibration_level_db: float = 94.0   # field check level
    mic_height_m: float = 1.5            # microphone height above ground
    # Meteorology during the survey. A sound level meter carries no weather
    # sensors, so these are entered by the team exactly as they are in BSA's
    # manual reports — wind and temperature affect propagation, and the
    # regulator's format carries them as a table. Left blank, the table is
    # omitted rather than printed empty.
    met_temp_max_c: Optional[float] = None
    met_temp_min_c: Optional[float] = None
    met_rh_max_pct: Optional[float] = None
    met_rh_min_pct: Optional[float] = None
    met_wind_max_ms: Optional[float] = None
    met_wind_min_ms: Optional[float] = None
    met_wind_mean_ms: Optional[float] = None
    met_wind_prevailing: Optional[str] = None
    # Free text describing what was happening at the location during the
    # survey — the "site conditions" the manual report records.
    site_conditions_note: Optional[str] = None


class CampaignCreate(CampaignBase):
    pass


class CampaignUpdate(BaseModel):
    gas_units: Optional[str] = None
    gas_units_map: Optional[Dict[str, str]] = None
    document_status: Optional[str] = None
    facility_latitude: Optional[float] = None
    facility_longitude: Optional[float] = None
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
    campaign_type: Optional[str] = None
    noise_category: Optional[str] = None
    day_start_hour: Optional[int] = None
    day_end_hour: Optional[int] = None
    construction_base_category: Optional[str] = None
    construction_hours_per_day: Optional[float] = None
    meter_model: Optional[str] = None
    meter_serial: Optional[str] = None
    calibrator_model: Optional[str] = None
    calibration_level_db: Optional[float] = None
    mic_height_m: Optional[float] = None
    met_temp_max_c: Optional[float] = None
    met_temp_min_c: Optional[float] = None
    met_rh_max_pct: Optional[float] = None
    met_rh_min_pct: Optional[float] = None
    met_wind_max_ms: Optional[float] = None
    met_wind_min_ms: Optional[float] = None
    met_wind_mean_ms: Optional[float] = None
    met_wind_prevailing: Optional[str] = None
    site_conditions_note: Optional[str] = None


class Campaign(CampaignBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    station_id: Optional[str] = None
    instruments: List["Instrument"] = Field(default_factory=list)
    # draft | ingested | ready | submitted | approved | archived
    # submitted and approved are set by the review workflow (routes/review.py);
    # returning a campaign puts it back to ready so it can be resubmitted.
    status: str = "draft"
    submitted_by: Optional[str] = None
    submitted_by_id: Optional[str] = None
    submitted_at: Optional[datetime] = None
    submitted_report_id: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    returned_by: Optional[str] = None
    returned_at: Optional[datetime] = None
    review_comment: Optional[str] = None
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


class NoiseReading(BaseModel):
    """One logged sound-level interval — typically one minute of LAeq."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    campaign_id: str
    timestamp: datetime
    laeq: float                        # dB(A)
    valid: bool = True
    invalidation_reason: Optional[str] = None
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
    # Units actually applied to each gas column, and where each came from
    # ("file" | "campaign" | "campaign (legacy)"). Recorded so a report can
    # always be traced back to the conversion that produced its numbers.
    units_applied: Dict[str, str] = Field(default_factory=dict)
    units_warnings: List[str] = Field(default_factory=list)
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
    mdl_ugm3: Optional[float] = None      # detection limit applied, µg/m³
    below_mdl_count: int = 0              # hours below that limit
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
    mdl_ugm3: Optional[float] = None    # method detection limit, µg/m³


class StationBase(BaseModel):
    """A piece of monitoring equipment held in the library, saved once and
    loaded into any campaign.

    Two kinds share this record because everything about them is the same:
    an instrument list, calibration certificates that belong to the
    equipment rather than the job, and a photograph. An ``air`` station is a
    mobile laboratory of analysers; a ``noise`` station is a sound level
    meter and its calibrator. Keeping one registry means the certificate
    selection, the audit trail and the storage paths are written once.
    """
    kind: str = "air"                   # "air" | "noise"
    name: str                           # e.g. "Mobile Lab 2", "Cirrus CR:171B"
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
    kind: Optional[str] = None
    name: Optional[str] = None
    code: Optional[str] = None
    notes: Optional[str] = None
    instruments: Optional[List[Instrument]] = None


# ---------------------------------------------------------------------------
# Attachments — field photos, calibration certificates, licence, site map
# ---------------------------------------------------------------------------
ATTACHMENT_KINDS = ("site_photo", "calibration", "license", "site_map",
                    "cover_photo", "equipment_photo")


class Attachment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    # A certificate normally belongs to the ANALYSER, so it is stored against
    # the mobile lab and reused by every campaign that lab runs. Photos and
    # one-off certificates stay on the campaign.
    campaign_id: str = ""
    station_id: Optional[str] = None
    # A cover photo lives once in the shared library (campaign_id and
    # station_id both empty) and is pointed at by each campaign that uses it.
    # source_id names the library record, so deleting the original can find
    # and clear every campaign still referring to it.
    source_id: Optional[str] = None
    kind: str                           # one of ATTACHMENT_KINDS
    filename: str
    path: str
    caption: Optional[str] = None
    instrument_sn: Optional[str] = None  # links a certificate to Table 4
    # Optional calibration-certificate metadata. When supplied, Appendix 3
    # opens with a summary table; left blank, only the scans are printed.
    cert_number: Optional[str] = None
    cert_parameter: Optional[str] = None
    cert_model_sn: Optional[str] = None
    cert_date: Optional[str] = None
    cert_due_date: Optional[str] = None
    cert_result: Optional[str] = None
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
    cert_number: Optional[str] = None
    cert_parameter: Optional[str] = None
    cert_model_sn: Optional[str] = None
    cert_date: Optional[str] = None
    cert_due_date: Optional[str] = None
    cert_result: Optional[str] = None


Campaign.model_rebuild()
CampaignUpdate.model_rebuild()
