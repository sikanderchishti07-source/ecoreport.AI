# -*- coding: utf-8 -*-
"""Soil and water reporting: parameter profiles, samples, results, evaluation.

Three things live here.

**Parameter profiles.** Different clients ask for different suites, so the
list of parameters is not a fixed schema — it is data, chosen per campaign
and saveable under a name so the next job for the same client is one click.

**Laboratory samples.** One campaign holds many samples. A site visit that
produces four water samples and four soil samples is one campaign with
eight samples in it, and the report puts them side by side. Each sample
carries its own context — particle size, land use, depth, water body class
— because that context is what selects the limit it is judged against.

**The results grid.** Results arrive as a rectangle: parameters down,
sample codes across. That is how a laboratory reports a multi-point job and
it is how the report prints, so it is how the ingest accepts it. Uploading
one sheet per sample and stitching them together afterwards is the same
work done three times.

The ingest never invents. A parameter name it cannot resolve is stored with
the name exactly as written and marked unresolved, so it appears in the
report with its result and no verdict, rather than being quietly matched to
a different parameter or dropped.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import (APIRouter, Depends, File, HTTPException, Response,
                     UploadFile, status)
from pydantic import BaseModel, Field

import sample_calc
import soil_water_limits as L
from audit import audit
from auth import current_username
from db import db, from_mongo, to_mongo
from sample_models import (
    MEDIUM_LABELS,
    MEDIUM_REPORT_TITLES,
    SAMPLE_MEDIA,
    STANDARDS_BY_MEDIUM,
    AnalyteResult,
    LabSample,
    ParameterProfile,
    ParameterProfileCreate,
    ParameterProfileUpdate,
    SampleCampaignSettings,
    SampleCampaignSummary,
    SampleContext,
    SampleCreate,
    SampleUpdate,
    utcnow,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["soil-water"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _campaign_or_404(campaign_id: str) -> Dict[str, Any]:
    doc = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return doc


def _settings_of(campaign: Dict[str, Any]) -> SampleCampaignSettings:
    """An absent settings block means all defaults, which means no standard,
    which means no verdicts. That is the correct posture for a campaign
    nobody has configured yet, not an error."""
    return SampleCampaignSettings(**(campaign.get("sample_settings") or {}))


async def _samples_of(campaign_id: str) -> List[LabSample]:
    cursor = db.lab_samples.find({"campaign_id": campaign_id}, {"_id": 0})
    docs = await cursor.to_list(length=500)
    docs.sort(key=lambda d: (d.get("position", 0), d.get("code", "")))
    return [LabSample(**d) for d in docs]


def _parse_number(text: Any) -> Tuple[Optional[float], Optional[str], bool]:
    """Read one cell of a results grid.

    Returns (value, raw_text, below_loq).

    A result written "<0.001" is below the laboratory's limit of
    quantification. It is kept as written and flagged; it is never turned
    into 0.001, and never into zero. Anything unparseable is kept as text
    with no value, so it prints as the laboratory wrote it and is not judged.
    """
    if text is None:
        return None, None, False
    raw = str(text).strip()
    if not raw or raw.lower() in {"-", "na", "n/a", "nd", "\u2014"}:
        return None, (raw or None), False
    cleaned = raw.replace(",", "").replace("\u2212", "-")
    below = cleaned.startswith("<")
    if below:
        cleaned = cleaned[1:].strip()
    try:
        return float(cleaned), raw, below
    except ValueError:
        return None, raw, False


# ---------------------------------------------------------------------------
# Analyte library and profiles
# ---------------------------------------------------------------------------
@router.get("/analytes")
async def list_analytes(medium: Optional[str] = None) -> Dict[str, Any]:
    """The master parameter list a profile is built from."""
    items = L.analytes_for(medium) if medium else list(L.ANALYTES)
    return {
        "analytes": [
            {"key": a.key, "name": a.name, "group": a.group,
             "unit": a.unit, "method": a.method, "media": list(a.media)}
            for a in items
        ],
        "groups": [{"key": g, "label": sample_calc.GROUP_LABELS.get(g, g)}
                   for g in sample_calc.GROUP_ORDER],
    }


@router.get("/standards")
async def list_standards() -> Dict[str, Any]:
    """The standards a campaign can be judged against, and the context each
    one requires. The frontend uses this to decide which fields to show and
    which are mandatory before a verdict is possible."""
    return {
        "media": [{"key": m, "label": MEDIUM_LABELS[m],
                   "title": MEDIUM_REPORT_TITLES[m],
                   "standards": list(STANDARDS_BY_MEDIUM[m])}
                  for m in SAMPLE_MEDIA],
        "standards": [
            {"key": "ncec_soil",
             "label": "NCEC — soil (Prevention and Remediation of Soil Pollution, Appendix 1)",
             "media": ["soil"],
             "requires": ["particle_size", "land_use", "depth"]},
            {"key": "ncec_water_ambient",
             "label": "NCEC — ambient water (Protection of Aqueous Media, Appendix 1)",
             "media": ["water"],
             "requires": ["water_medium"]},
            {"key": "ncec_water_discharge",
             "label": "NCEC — treated wastewater discharge (Appendices 2 and 3)",
             "media": ["water"],
             "requires": ["discharge_destination"]},
            {"key": "ads_81_2017",
             "label": "Abu Dhabi ADS 81/2017 — sediment (limits not yet held)",
             "media": ["sediment"], "requires": []},
            {"key": "none", "label": "No standard — report results only",
             "media": ["soil", "water", "sediment"], "requires": []},
        ],
        "land_uses": [{"key": k, "label": L.LAND_USE_LABELS[k]} for k in L.LAND_USES],
        "particle_sizes": [{"key": k, "label": L.PARTICLE_SIZE_LABELS[k]}
                           for k in L.PARTICLE_SIZES],
        "depths": [{"key": k, "label": L.DEPTH_LABELS[k]} for k in L.DEPTHS],
        "water_media": [{"key": k, "label": L.WATER_MEDIA_LABELS[k]}
                        for k in L.WATER_MEDIA],
        "discharge_destinations": [
            {"key": k, "label": L.DISCHARGE_DESTINATION_LABELS[k]}
            for k in L.DISCHARGE_DESTINATIONS],
        "decision_rules": [
            {"key": "simple_acceptance",
             "label": "Simple acceptance (ILAC-G8:2019)"},
            {"key": "guard_band",
             "label": "Guard band — result widened by its measurement uncertainty"},
        ],
    }


@router.get("/parameter-profiles", response_model=List[ParameterProfile])
async def list_profiles(medium: Optional[str] = None,
                        client: Optional[str] = None) -> List[ParameterProfile]:
    query: Dict[str, Any] = {}
    if medium:
        query["medium"] = medium
    if client:
        # A profile with no client is available to every client.
        query["$or"] = [{"client": client}, {"client": None}]
    cursor = db.parameter_profiles.find(query, {"_id": 0}).sort("name", 1)
    docs = await cursor.to_list(length=500)
    return [ParameterProfile(**d) for d in docs]


@router.post("/parameter-profiles", response_model=ParameterProfile,
             status_code=status.HTTP_201_CREATED)
async def create_profile(payload: ParameterProfileCreate,
                         x_user: str = Depends(current_username)) -> ParameterProfile:
    unknown = [k for k in payload.analyte_keys if k not in L.ANALYTES_BY_KEY]
    if unknown:
        raise HTTPException(status_code=400,
                            detail=f"Unknown parameters: {', '.join(unknown)}")
    profile = ParameterProfile(**payload.model_dump(), created_by=x_user)
    await db.parameter_profiles.insert_one(to_mongo(profile.model_dump()))
    await audit("profile.create", "parameter_profile", profile.id, x_user,
                {"name": profile.name, "count": len(profile.analyte_keys)})
    return profile


@router.put("/parameter-profiles/{profile_id}", response_model=ParameterProfile)
async def update_profile(profile_id: str, payload: ParameterProfileUpdate,
                         x_user: str = Depends(current_username)) -> ParameterProfile:
    doc = await db.parameter_profiles.find_one({"id": profile_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Profile not found")
    changes = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "analyte_keys" in changes:
        unknown = [k for k in changes["analyte_keys"] if k not in L.ANALYTES_BY_KEY]
        if unknown:
            raise HTTPException(status_code=400,
                                detail=f"Unknown parameters: {', '.join(unknown)}")
    if changes:
        changes["updated_at"] = utcnow()
        await db.parameter_profiles.update_one({"id": profile_id},
                                               {"$set": to_mongo(changes)})
        await audit("profile.update", "parameter_profile", profile_id, x_user,
                    {"fields": sorted(changes)})
        doc.update(changes)
    return ParameterProfile(**from_mongo(doc))


@router.delete("/parameter-profiles/{profile_id}",
               status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_profile(profile_id: str,
                         x_user: str = Depends(current_username)) -> Response:
    res = await db.parameter_profiles.delete_one({"id": profile_id})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Profile not found")
    await audit("profile.delete", "parameter_profile", profile_id, x_user, {})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Campaign settings
# ---------------------------------------------------------------------------
@router.get("/campaigns/{campaign_id}/sample-settings",
            response_model=SampleCampaignSettings)
async def get_settings(campaign_id: str) -> SampleCampaignSettings:
    return _settings_of(await _campaign_or_404(campaign_id))


@router.put("/campaigns/{campaign_id}/sample-settings",
            response_model=SampleCampaignSettings)
async def put_settings(campaign_id: str, payload: SampleCampaignSettings,
                       x_user: str = Depends(current_username)
                       ) -> SampleCampaignSettings:
    await _campaign_or_404(campaign_id)
    if payload.medium not in STANDARDS_BY_MEDIUM:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown medium: {payload.medium}. "
                   f"Expected one of {', '.join(STANDARDS_BY_MEDIUM)}.")
    allowed = STANDARDS_BY_MEDIUM[payload.medium]
    if payload.standard not in allowed:
        # A water campaign judged against the soil table would produce a
        # compliance conclusion against the wrong document entirely. Refused
        # here rather than left to the engine to shrug at.
        raise HTTPException(
            status_code=400,
            detail=f"The standard {payload.standard} does not apply to a "
                   f"{payload.medium} campaign.")
    unknown = [k for k in payload.analyte_keys if k not in L.ANALYTES_BY_KEY]
    if unknown:
        raise HTTPException(status_code=400,
                            detail=f"Unknown parameters: {', '.join(unknown)}")
    wrong_medium = [k for k in payload.analyte_keys
                    if payload.medium not in L.ANALYTES_BY_KEY[k].media]
    if wrong_medium:
        names = ", ".join(L.ANALYTES_BY_KEY[k].name for k in wrong_medium)
        raise HTTPException(
            status_code=400,
            detail=f"Not {payload.medium} parameters: {names}")
    await db.campaigns.update_one(
        {"id": campaign_id},
        {"$set": to_mongo({"sample_settings": payload.model_dump(),
                           "updated_at": utcnow()})},
    )
    await audit("campaign.sample_settings", "campaign", campaign_id, x_user,
                {"medium": payload.medium,
                 "standard": payload.standard,
                 "decision_rule": payload.decision_rule,
                 "parameters": len(payload.analyte_keys)})
    return payload


# ---------------------------------------------------------------------------
# Samples
# ---------------------------------------------------------------------------
@router.get("/campaigns/{campaign_id}/samples", response_model=List[LabSample])
async def list_samples(campaign_id: str) -> List[LabSample]:
    await _campaign_or_404(campaign_id)
    return await _samples_of(campaign_id)


@router.post("/campaigns/{campaign_id}/samples", response_model=LabSample,
             status_code=status.HTTP_201_CREATED)
async def create_sample(campaign_id: str, payload: SampleCreate,
                        x_user: str = Depends(current_username)) -> LabSample:
    campaign = await _campaign_or_404(campaign_id)
    existing = await db.lab_samples.count_documents({"campaign_id": campaign_id})
    data = payload.model_dump()
    data["campaign_id"] = campaign_id
    # A sample in a water campaign is a water sample. Taking the medium from
    # the campaign rather than the request means a stale default in the
    # caller cannot put a soil sample in a water report.
    data["medium"] = _settings_of(campaign).medium
    sample = LabSample(**data, position=existing)
    if not sample.label:
        sample.label = f"S{existing + 1:02d}"
    try:
        await db.lab_samples.insert_one(to_mongo(sample.model_dump()))
    except Exception as exc:  # duplicate code within the campaign
        if "duplicate" in str(exc).lower():
            raise HTTPException(
                status_code=409,
                detail=f"A sample with code {sample.code} already exists "
                       "in this campaign") from exc
        raise
    await audit("sample.create", "lab_sample", sample.id, x_user,
                {"campaign_id": campaign_id, "code": sample.code})
    return sample


@router.put("/samples/{sample_id}", response_model=LabSample)
async def update_sample(sample_id: str, payload: SampleUpdate,
                        x_user: str = Depends(current_username)) -> LabSample:
    doc = await db.lab_samples.find_one({"id": sample_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Sample not found")
    changes = {k: v for k, v in payload.model_dump(exclude_unset=True).items()
               if v is not None}
    if changes:
        changes["updated_at"] = utcnow()
        await db.lab_samples.update_one({"id": sample_id},
                                        {"$set": to_mongo(changes)})
        await audit("sample.update", "lab_sample", sample_id, x_user,
                    {"fields": sorted(changes)})
        doc.update(changes)
    return LabSample(**from_mongo(doc))


@router.delete("/samples/{sample_id}", status_code=status.HTTP_204_NO_CONTENT,
               response_class=Response)
async def delete_sample(sample_id: str,
                        x_user: str = Depends(current_username)) -> Response:
    doc = await db.lab_samples.find_one({"id": sample_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Sample not found")
    await db.lab_samples.delete_one({"id": sample_id})
    await audit("sample.delete", "lab_sample", sample_id, x_user,
                {"campaign_id": doc.get("campaign_id"), "code": doc.get("code")})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Results grid
# ---------------------------------------------------------------------------
class GridCell(BaseModel):
    sample_code: str
    value: Optional[str] = None


class GridRow(BaseModel):
    """One parameter across every sample."""
    parameter: str
    unit: Optional[str] = None
    method: Optional[str] = None
    loq: Optional[float] = None
    mu_percent: Optional[float] = None
    cells: List[GridCell] = Field(default_factory=list)


class GridPayload(BaseModel):
    rows: List[GridRow] = Field(default_factory=list)
    # Codes not already present are created as samples, in this order, so a
    # paste can bring its own columns with it.
    create_missing_samples: bool = True
    medium: str = "soil"
    # Parameters found in the sheet are added to the campaign's scope.
    #
    # Only ever added. A parameter ticked by hand that the laboratory did not
    # report stays in the scope and prints as an empty row, which is the
    # honest outcome — it was in the scope of work and was not determined.
    # Silently dropping it would hide that.
    add_parameters_to_scope: bool = True


class GridIngestReport(BaseModel):
    """What the ingest did, in the same shape the upload log takes for air
    and noise: never a bare success, always what was accepted, what was
    created, and what could not be understood."""
    samples_matched: List[str] = Field(default_factory=list)
    samples_created: List[str] = Field(default_factory=list)
    parameters_resolved: int = 0
    parameters_unresolved: List[str] = Field(default_factory=list)
    # Names added to the campaign's parameter list by this upload.
    parameters_added: List[str] = Field(default_factory=list)
    # Resolved, but not valid for this campaign's medium — a soil parameter
    # on a water campaign. Stored with the result, never added to the scope.
    parameters_wrong_medium: List[str] = Field(default_factory=list)
    values_stored: int = 0
    # Values that overwrote an existing result for the same parameter and
    # sample. Everything else was added alongside what was already there.
    values_replaced: int = 0
    values_below_loq: int = 0
    values_unparsed: List[str] = Field(default_factory=list)


@router.post("/campaigns/{campaign_id}/results-grid",
             response_model=GridIngestReport)
async def ingest_grid(campaign_id: str, payload: GridPayload,
                      x_user: str = Depends(current_username)) -> GridIngestReport:
    """Store a rectangle of results: parameters down, sample codes across."""
    campaign = await _campaign_or_404(campaign_id)
    settings = _settings_of(campaign)
    report = GridIngestReport()

    existing = {s.code: s for s in await _samples_of(campaign_id)}
    wanted: List[str] = []
    for row in payload.rows:
        for cell in row.cells:
            if cell.sample_code and cell.sample_code not in wanted:
                wanted.append(cell.sample_code)

    position = len(existing)
    for code in wanted:
        if code in existing:
            report.samples_matched.append(code)
            continue
        if not payload.create_missing_samples:
            continue
        sample = LabSample(campaign_id=campaign_id, code=code,
                           label=code, medium=payload.medium,
                           position=position)
        await db.lab_samples.insert_one(to_mongo(sample.model_dump()))
        existing[code] = sample
        report.samples_created.append(code)
        position += 1

    # Results are merged per parameter, not rebuilt per sample.
    #
    # A laboratory commonly sends one sheet per method group — organics on
    # one, metals on another. Rebuilding the sample wholesale meant the
    # second upload silently erased the first, with the report looking
    # complete and simply missing half its rows. Merging by parameter means a
    # re-upload of the same sheet replaces those parameters and leaves the
    # rest standing.
    collected: Dict[str, Dict[str, AnalyteResult]] = {
        code: {(r.analyte_key if r.resolved else (r.reported_name or r.analyte_key)): r
               for r in sample.results}
        for code, sample in existing.items()
    }
    replaced = 0
    found_keys: List[str] = []

    for row in payload.rows:
        analyte = L.resolve_analyte(row.parameter)
        if analyte is None:
            if row.parameter not in report.parameters_unresolved:
                report.parameters_unresolved.append(row.parameter)
        else:
            report.parameters_resolved += 1
            if settings.medium not in analyte.media:
                if analyte.name not in report.parameters_wrong_medium:
                    report.parameters_wrong_medium.append(analyte.name)
            elif analyte.key not in found_keys:
                found_keys.append(analyte.key)
        for cell in row.cells:
            if cell.sample_code not in collected:
                continue
            value, raw, below = _parse_number(cell.value)
            if value is None and raw is None:
                continue
            if value is None and raw and not below:
                label = f"{row.parameter} / {cell.sample_code}: {raw}"
                if label not in report.values_unparsed:
                    report.values_unparsed.append(label)
            slot = (analyte.key if analyte else row.parameter)
            if slot in collected[cell.sample_code]:
                replaced += 1
            collected[cell.sample_code][slot] = (AnalyteResult(
                analyte_key=analyte.key if analyte else row.parameter,
                reported_name=row.parameter,
                value=value,
                raw_value=raw,
                below_loq=below,
                unit=row.unit or (analyte.unit if analyte else None),
                method=row.method or (analyte.method if analyte else None),
                loq=row.loq,
                mu_percent=row.mu_percent,
                resolved=analyte is not None,
            ))
            report.values_stored += 1
            if below:
                report.values_below_loq += 1

    for code, table in collected.items():
        sample = existing[code]
        await db.lab_samples.update_one(
            {"id": sample.id},
            {"$set": to_mongo({"results": [r.model_dump() for r in table.values()],
                               "updated_at": utcnow()})},
        )
    report.values_replaced = replaced

    # Extend the scope with whatever the sheet turned out to contain. Union,
    # in the order the campaign already had, then anything new.
    if payload.add_parameters_to_scope and found_keys:
        scope = list(settings.analyte_keys)
        added = [k for k in found_keys if k not in scope]
        if added:
            settings.analyte_keys = scope + added
            await db.campaigns.update_one(
                {"id": campaign_id},
                {"$set": to_mongo({"sample_settings": settings.model_dump(),
                                   "updated_at": utcnow()})},
            )
            report.parameters_added = [L.ANALYTES_BY_KEY[k].name for k in added]

    await audit("sample.grid_ingest", "campaign", campaign_id, x_user, {
        "samples": len(collected),
        "values": report.values_stored,
        "unresolved": report.parameters_unresolved,
        "added_to_scope": report.parameters_added,
    })
    if report.parameters_unresolved:
        log.info("Grid ingest on %s: %d parameter name(s) not resolved: %s",
                 campaign_id, len(report.parameters_unresolved),
                 ", ".join(report.parameters_unresolved))
    return report


@router.post("/campaigns/{campaign_id}/results-csv",
             response_model=GridIngestReport)
async def ingest_csv(campaign_id: str,
                     file: UploadFile = File(...),
                     add_parameters_to_scope: bool = True,
                     x_user: str = Depends(current_username)) -> GridIngestReport:
    """Same rectangle, uploaded as CSV.

    First column is the parameter name. A column headed Unit, Method, LOQ or
    MU% is metadata; every other column is a sample code. Column order is
    not assumed — the header row is read.
    """
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise HTTPException(status_code=400, detail="The file is empty")

    meta = {"unit": None, "method": None, "loq": None, "mu%": None,
            "mu": None, "mu percent": None}
    sample_cols: List[Tuple[int, str]] = []
    meta_cols: Dict[str, int] = {}
    for idx, name in enumerate(header):
        label = (name or "").strip()
        if idx == 0:
            continue
        if label.lower() in meta:
            meta_cols[label.lower()] = idx
        elif label:
            sample_cols.append((idx, label))
    if not sample_cols:
        raise HTTPException(
            status_code=400,
            detail="No sample columns found. The first column is the "
                   "parameter name; every other column heading is read as a "
                   "sample code.")

    def cell(row: List[str], idx: Optional[int]) -> Optional[str]:
        if idx is None or idx >= len(row):
            return None
        return row[idx].strip() or None

    rows: List[GridRow] = []
    for line in reader:
        if not line or not (line[0] or "").strip():
            continue
        loq_raw = cell(line, meta_cols.get("loq"))
        mu_raw = cell(line, meta_cols.get("mu%") or meta_cols.get("mu")
                      or meta_cols.get("mu percent"))
        loq_val, _, _ = _parse_number(loq_raw)
        mu_val, _, _ = _parse_number((mu_raw or "").replace("±", "").replace("%", ""))
        rows.append(GridRow(
            parameter=line[0].strip(),
            unit=cell(line, meta_cols.get("unit")),
            method=cell(line, meta_cols.get("method")),
            loq=loq_val,
            mu_percent=mu_val,
            cells=[GridCell(sample_code=code, value=cell(line, idx))
                   for idx, code in sample_cols],
        ))

    campaign = await _campaign_or_404(campaign_id)
    settings = _settings_of(campaign)
    return await ingest_grid(
        campaign_id,
        GridPayload(rows=rows, medium=settings.medium,
                    add_parameters_to_scope=add_parameters_to_scope),
        x_user)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
@router.get("/campaigns/{campaign_id}/sample-summary",
            response_model=SampleCampaignSummary)
async def sample_summary(campaign_id: str) -> SampleCampaignSummary:
    """The evaluated matrix. This is what the report generator reads and
    what the review screen shows."""
    campaign = await _campaign_or_404(campaign_id)
    settings = _settings_of(campaign)
    samples = await _samples_of(campaign_id)
    return sample_calc.evaluate(campaign_id, settings, samples)


@router.get("/campaigns/{campaign_id}/land-use-comparison")
async def land_use_comparison(campaign_id: str) -> Dict[str, Any]:
    """All five land-use columns for the campaign's parameters.

    Printed as an appendix so a reviewer can see at a glance what the same
    results would have been judged against under a different land use. This
    is the table that makes a wrong land use obvious instead of invisible.
    """
    campaign = await _campaign_or_404(campaign_id)
    settings = _settings_of(campaign)
    ctx = settings.default_context
    if settings.standard != "ncec_soil" or ctx.particle_size not in L.PARTICLE_SIZES:
        return {"applicable": False, "rows": [], "land_uses": list(L.LAND_USES),
                "reason": "This table applies to soil campaigns with a "
                          "recorded particle size."}
    keys = settings.analyte_keys
    if not keys:
        keys = [r.analyte_key for s in await _samples_of(campaign_id)
                for r in s.results]
    return {
        "applicable": True,
        "particle_size": ctx.particle_size,
        "depth": ctx.depth,
        "applied_land_use": ctx.land_use,
        "land_uses": [{"key": k, "label": L.LAND_USE_LABELS[k]} for k in L.LAND_USES],
        "rows": sample_calc.land_use_comparison(keys, ctx.particle_size, ctx.depth),
        "source": L.SOIL_SOURCE,
    }


@router.get("/campaigns/{campaign_id}/sample-readiness")
async def sample_readiness(campaign_id: str) -> Dict[str, Any]:
    """What is still missing before this campaign can be reported.

    Kept separate from the summary so the wizard can show it before anyone
    presses generate. Every entry is a thing a person has to decide, not a
    thing the system could work out for itself.
    """
    campaign = await _campaign_or_404(campaign_id)
    settings = _settings_of(campaign)
    samples = await _samples_of(campaign_id)
    blocking: List[str] = []
    warnings: List[str] = []

    if settings.standard == "none":
        blocking.append("No standard selected, so nothing can be assessed.")
    if not samples:
        blocking.append("No samples recorded.")
    if not settings.analyte_keys:
        warnings.append("No parameter list chosen; every parameter present in "
                        "the results will be printed.")

    for sample in samples:
        merged = settings.default_context.model_dump()
        for key, value in sample.context.model_dump().items():
            if key == "is_single_sample" or value is not None:
                merged[key] = value
        gaps = SampleContext(**merged).missing_for(sample.medium, settings.standard)
        if gaps:
            blocking.append(f"{sample.label or sample.code}: "
                            + ", ".join(gaps) + " not recorded.")
        if not sample.results:
            warnings.append(f"{sample.label or sample.code}: no results entered.")
        if not sample.laboratory and not settings.laboratory:
            warnings.append(f"{sample.label or sample.code}: no laboratory named.")

    if settings.decision_rule == "guard_band":
        missing_mu = [s.label or s.code for s in samples
                      if any(r.value is not None and r.mu_percent is None
                             for r in s.results)]
        if missing_mu:
            warnings.append(
                "A guard band was selected but measurement uncertainty is "
                "missing for: " + ", ".join(sorted(set(missing_mu)))
                + ". Those results will be compared as reported.")

    return {
        "ready": not blocking,
        "blocking": blocking,
        "warnings": sorted(set(warnings)),
        "sample_count": len(samples),
        "medium": settings.medium,
        "medium_label": MEDIUM_LABELS.get(settings.medium, settings.medium),
        "report_title": MEDIUM_REPORT_TITLES.get(settings.medium, "Monitoring campaign"),
        "standard": settings.standard,
        "decision_rule": settings.decision_rule,
    }
