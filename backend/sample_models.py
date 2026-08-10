"""Models for the soil and water reporting engine.

Kept in a file of their own rather than added to models.py. The air and
noise models are long and stable; a hand edit into the middle of them has
gone wrong on this project before, and nothing here needs to reach into
them. `campaign_type` on CampaignBase is a plain str, so "soil_water"
needs no change there either.

The shape is different from air and noise. Those are time series: one
station, many timestamps, statistics over a window. This is discrete
samples: several sample points, one laboratory result per parameter per
point, each judged against a limit chosen by the context recorded for that
sample.

One campaign therefore holds many samples, and one sample holds many
results. A site visit that produces four water samples and four soil
samples is one campaign with eight samples in it, and the report puts them
side by side.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from soil_water_limits import (
    DEPTHS,
    DISCHARGE_DESTINATIONS,
    LAND_USES,
    PARTICLE_SIZES,
    WATER_MEDIA,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# The media a sample can be. Sediment is included because BSA already
# reports it, but note that NCEC publishes no sediment table — sediment work
# is assessed against Abu Dhabi ADS 81/2017 on BSA's current certificates,
# which is why the standard is chosen per campaign rather than assumed.
SAMPLE_MEDIA = ("water", "soil", "sediment")

# Which regulation a campaign is judged against. Held on the campaign, not
# hardcoded in the engine, for the same reason the air engine needs a
# standard selector before a NEOM job is run through it.
STANDARDS = ("ncec_soil", "ncec_water_ambient", "ncec_water_discharge",
             "ads_81_2017", "none")

# How a statement of conformity is made, per ILAC-G8:2019. Simple acceptance
# compares the result to the limit as reported. A guard band requires the
# result plus its expanded measurement uncertainty to sit inside the limit,
# so a result just under the limit can still fail. BSA's issued certificates
# use simple acceptance; the field is explicit so the report can say which
# was applied instead of leaving a reader to assume.
DECISION_RULES = ("simple_acceptance", "guard_band")


# ---------------------------------------------------------------------------
# Parameter profile — the client's required list
# ---------------------------------------------------------------------------
class ParameterProfile(BaseModel):
    """A reusable list of analytes for a client or a kind of job.

    Different clients ask for different suites. Rather than a fixed schema
    of columns, a campaign carries the list of analyte keys it determined,
    and a profile is that list saved under a name so the next job for the
    same client is one click.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    medium: str = "soil"              # one of SAMPLE_MEDIA
    client: Optional[str] = None      # None => available to every client
    analyte_keys: List[str] = Field(default_factory=list)
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ParameterProfileCreate(BaseModel):
    name: str
    medium: str = "soil"
    client: Optional[str] = None
    analyte_keys: List[str] = Field(default_factory=list)


class ParameterProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: Optional[str] = None
    client: Optional[str] = None
    analyte_keys: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Sample context — the fields that choose the limit
# ---------------------------------------------------------------------------
class SampleContext(BaseModel):
    """Everything needed to pick the right column of the right appendix.

    Every field is optional and every field defaults to unset. That is
    deliberate: an unset field produces no verdict rather than a verdict
    against a guessed column. Appendix (1) of the soil regulation has five
    land-use columns and the spread between them is wide — F1 hydrocarbons
    are 24 mg/kg on agricultural land and 270 on commercial.
    """
    model_config = ConfigDict(extra="ignore")

    # --- soil and sediment ---
    particle_size: Optional[str] = None    # coarse | soft        (Article 1)
    land_use: Optional[str] = None         # one of LAND_USES     (Appendix 1)
    depth: Optional[str] = None            # topsoil | subsurface (Appendix 1)
    depth_from_m: Optional[float] = None
    depth_to_m: Optional[float] = None

    # --- ambient water ---
    water_medium: Optional[str] = None     # one of WATER_MEDIA   (Table 1)

    # --- treated wastewater ---
    discharge_destination: Optional[str] = None   # DISCHARGE_DESTINATIONS
    is_single_sample: bool = True          # a grab sample, not a 30-day set

    def missing_for(self, medium: str, standard: str) -> List[str]:
        """Which context fields are still needed before a verdict is possible.

        Returned in words fit to show a reviewer, because this is exactly
        the thing that goes wrong quietly.
        """
        gaps: List[str] = []
        if standard in ("ncec_soil", "ads_81_2017") or medium in ("soil", "sediment"):
            if self.particle_size not in PARTICLE_SIZES:
                gaps.append("soil particle size (coarse or soft)")
            if self.land_use not in LAND_USES:
                gaps.append("land use")
            if self.depth not in DEPTHS:
                gaps.append("sampling depth (topsoil or subsurface)")
        if standard == "ncec_water_ambient":
            if self.water_medium not in WATER_MEDIA:
                gaps.append("water body class")
        if standard == "ncec_water_discharge":
            if self.discharge_destination not in DISCHARGE_DESTINATIONS:
                gaps.append("discharge destination")
        return gaps


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
class AnalyteResult(BaseModel):
    """One laboratory determination.

    `value` is None when the parameter was not determined. `below_loq` marks
    a result the laboratory reported as less than its limit of
    quantification — printed as reported and never called an exceedance,
    and never silently turned into zero.
    """
    model_config = ConfigDict(extra="ignore")

    analyte_key: str
    # The name exactly as it appeared on the laboratory sheet. Kept so an
    # unresolved parameter can still be printed, and so a reviewer can see
    # what was matched to what.
    reported_name: Optional[str] = None
    value: Optional[float] = None
    raw_value: Optional[str] = None       # e.g. "<0.001"
    below_loq: bool = False
    unit: Optional[str] = None
    method: Optional[str] = None
    loq: Optional[float] = None
    mu_percent: Optional[float] = None    # expanded measurement uncertainty
    resolved: bool = True                 # False => name not in the library


class SampleBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    campaign_id: str
    code: str                             # e.g. "BSA 03-08-2026 S01"
    label: str = ""                       # e.g. "S01" — the report column head
    medium: str = "soil"                  # one of SAMPLE_MEDIA
    location_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    sampled_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    reported_at: Optional[datetime] = None
    sampled_by: Optional[str] = None
    laboratory: Optional[str] = None
    lab_accreditation: Optional[str] = None
    coc_number: Optional[str] = None      # chain of custody reference
    context: SampleContext = Field(default_factory=SampleContext)
    results: List[AnalyteResult] = Field(default_factory=list)
    note: Optional[str] = None
    # Linked back to the field visit that produced it, where there was one.
    visit_id: Optional[str] = None
    sample_record_id: Optional[str] = None   # id in the site_samples collection


class SampleCreate(SampleBase):
    pass


class SampleUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: Optional[str] = None
    label: Optional[str] = None
    medium: Optional[str] = None
    location_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    sampled_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    reported_at: Optional[datetime] = None
    sampled_by: Optional[str] = None
    laboratory: Optional[str] = None
    lab_accreditation: Optional[str] = None
    coc_number: Optional[str] = None
    context: Optional[SampleContext] = None
    results: Optional[List[AnalyteResult]] = None
    note: Optional[str] = None


class LabSample(SampleBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    position: int = 0                      # column order in the report
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# Evaluation output — what the report prints
# ---------------------------------------------------------------------------
class CellEvaluation(BaseModel):
    """One analyte in one sample, judged."""
    sample_id: str
    sample_label: str
    analyte_key: str
    analyte_name: str
    unit: str
    value: Optional[float] = None
    display_value: str = "\u2014"
    below_loq: bool = False
    limit_display: str = "No limit"
    limit_value: Optional[float] = None
    limit_low: Optional[float] = None
    limit_high: Optional[float] = None
    direction: str = "max"
    # complies | exceeds | not_assessed
    verdict: str = "not_assessed"
    reason: Optional[str] = None
    percent_of_limit: Optional[float] = None
    source: Optional[str] = None


class SampleEvaluation(BaseModel):
    sample_id: str
    label: str
    code: str
    medium: str
    assessed_count: int = 0
    not_assessed_count: int = 0
    exceedance_count: int = 0
    # compliant | non_compliant | no_verdict
    outcome: str = "no_verdict"
    missing_context: List[str] = Field(default_factory=list)


class SampleCampaignSummary(BaseModel):
    """The whole campaign, evaluated. This is what the DOCX generator reads."""
    campaign_id: str
    standard: str
    decision_rule: str = "simple_acceptance"
    samples: List[SampleEvaluation] = Field(default_factory=list)
    # Row order follows the campaign's parameter profile, grouped for print.
    rows: List[Dict[str, object]] = Field(default_factory=list)
    cells: List[CellEvaluation] = Field(default_factory=list)
    total_exceedances: int = 0
    unresolved_names: List[str] = Field(default_factory=list)
    # Set when the campaign cannot be judged at all — printed in place of a
    # verdict rather than beside one.
    blocking_note: Optional[str] = None


class SampleCampaignSettings(BaseModel):
    """Soil and water fields that live on the campaign document.

    Stored inside the campaign record under `sample_settings` so models.py
    does not have to change. Reading code should treat an absent block as
    all-defaults, which means: no standard chosen, so no verdicts.
    """
    model_config = ConfigDict(extra="ignore")
    standard: str = "none"
    decision_rule: str = "simple_acceptance"
    analyte_keys: List[str] = Field(default_factory=list)
    profile_id: Optional[str] = None
    laboratory: Optional[str] = None
    lab_accreditation: Optional[str] = None
    # Applied to every sample unless the sample overrides it. One site is
    # usually one land use and one soil type; per-sample overrides exist for
    # the job where it is not.
    default_context: SampleContext = Field(default_factory=SampleContext)
