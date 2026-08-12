"""Soil and water evaluation engine.

Takes a campaign's settings and its laboratory samples, and produces the
matrix the report prints: one row per parameter, one column per sample,
each cell judged against the limit that the sample's own context selects.

Deliberate design points, each of them a lesson from the air and noise
engines:

* Nothing is assumed. A limit that cannot be established returns no
  verdict and a printed reason. There is no default land use, no default
  water body class and no fallback column.

* Every sample carries its own context. One site is usually one soil type
  and one land use, so a campaign default exists — but a sample may
  override it, because a job that crosses a boundary is exactly the job
  that gets judged against the wrong column.

* Direction is per parameter. Dissolved oxygen is a minimum and pH is a
  range. "Over the limit is bad" would pass an anoxic sample.

* A result below the laboratory limit of quantification is printed as the
  laboratory reported it and treated as compliant. It is never turned into
  zero, and never called an exceedance.

* Measurement uncertainty is applied only when the campaign says to. Under
  simple acceptance the result is compared as reported; under a guard band
  the result is widened by its expanded uncertainty first, so a result just
  inside the limit can still fail. Which rule was used is carried out to
  the report, because ILAC-G8 requires the statement of conformity to say.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import soil_water_limits as L
from sample_models import (
    CellEvaluation,
    LabSample,
    SampleCampaignSettings,
    SampleCampaignSummary,
    SampleContext,
    SampleEvaluation,
)

# Group order for printing. Parameters are grouped the way BSA's own
# certificates group them, not alphabetically.
GROUP_ORDER: Tuple[str, ...] = (
    "tph", "btex", "pah", "organics", "physicochemical", "chemical",
    "metals", "microbiology", "grain_size",
)
GROUP_LABELS: Dict[str, str] = {
    "tph": "Total petroleum hydrocarbons",
    "btex": "Volatile organic compounds \u2014 BTEX",
    "pah": "Polycyclic aromatic hydrocarbons",
    "organics": "Organic parameters",
    "physicochemical": "Physicochemical parameters",
    "chemical": "Chemical parameters",
    "metals": "Metals",
    "microbiology": "Microbiological parameters",
    "grain_size": "Grain size",
}

# Standards that carry no limit table in this system. ADS 81/2017 is the
# Abu Dhabi sediment specification BSA's certificates already cite; NCEC
# publishes no sediment table at all. Until the source document is in hand
# the engine reports results and gives no verdicts, rather than borrowing
# the soil table because it is the nearest thing available.
UNIMPLEMENTED_STANDARDS: Dict[str, str] = {
    "ads_81_2017": (
        "Abu Dhabi specification ADS 81/2017 is not held in this system. "
        "Results are reported without a compliance conclusion."
    ),
    "none": (
        "No standard has been selected for this campaign, so no compliance "
        "conclusion is drawn."
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _merge_context(default: SampleContext,
                   sample: SampleContext) -> SampleContext:
    """Sample context wins field by field; unset fields inherit the default.

    Field-by-field rather than whole-object, so a sample that overrides only
    its land use keeps the campaign's particle size instead of silently
    losing it.
    """
    merged = default.model_dump()
    for key, value in sample.model_dump().items():
        if key == "is_single_sample":
            # A boolean has no "unset", so the sample's value always applies.
            merged[key] = value
            continue
        if value is not None:
            merged[key] = value
    return SampleContext(**merged)


def _lookup(analyte: L.Analyte, standard: str, ctx: SampleContext) -> L.Limit:
    """The limit for one analyte under one standard in one context.

    Keyed on `analyte.key`, never on the printed name. The regulation and
    BSA's certificates spell several parameters differently — Appendix (1)
    writes "Mercury, inorganic (Hg)" and "pH (in 0.01M CaCl2)" — and
    matching on name returned "no limit" for both.
    """
    key = analyte.key
    if standard == "ncec_soil":
        return L.soil_limit(key, ctx.particle_size, ctx.land_use, ctx.depth)
    if standard == "ncec_water_ambient":
        return L.water_ambient_limit(key, ctx.water_medium)
    if standard == "ncec_water_discharge":
        return L.discharge_limit(key, ctx.discharge_destination,
                                 single_sample=ctx.is_single_sample)
    return L.Limit(analyte=analyte.name, unit=analyte.unit, assessable=False,
                   reason=UNIMPLEMENTED_STANDARDS.get(
                       standard, UNIMPLEMENTED_STANDARDS["none"]))


def _display(result) -> str:
    """The result as it should be printed."""
    if result is None:
        return "\u2014"
    if result.raw_value:
        return result.raw_value
    if result.value is None:
        return "\u2014"
    v = result.value
    if v == int(v) and abs(v) >= 1:
        return f"{int(v):,}"
    return f"{v:g}"


def _widen(value: float, mu_percent: Optional[float],
           direction: str) -> float:
    """Apply the expanded measurement uncertainty as a guard band.

    Under ILAC-G8 a guard band is a decision to require the result plus its
    uncertainty to sit inside the limit. Against a ceiling the result moves
    up; against a minimum it moves down. Without an uncertainty figure the
    result is returned unchanged — a missing MU cannot be treated as zero
    uncertainty, so the caller flags it separately.
    """
    if not mu_percent:
        return value
    delta = abs(value) * (mu_percent / 100.0)
    return value - delta if direction == "min" else value + delta


def _percent_of_limit(value: Optional[float], limit: L.Limit) -> Optional[float]:
    """Result as a percentage of the applicable limit, for the chart.

    Only meaningful against a ceiling. A minimum or a range has no single
    number to be a percentage of, so those return None rather than a figure
    that would plot misleadingly.
    """
    if value is None or not limit.assessable:
        return None
    if limit.direction != "max" or not limit.value:
        return None
    if value < 0 and not limit.allows_negative:
        return None
    return round(100.0 * value / limit.value, 1)


# ---------------------------------------------------------------------------
# Row ordering
# ---------------------------------------------------------------------------
def ordered_analytes(keys: Sequence[str]) -> List[L.Analyte]:
    """The campaign's parameter list, in print order, unknown keys dropped.

    Order within a group follows the order the keys were chosen, so a
    profile that lists F1 to F4 prints them in that order rather than
    alphabetically.
    """
    seen: set = set()
    picked: List[L.Analyte] = []
    for k in keys:
        if k in seen:
            continue
        seen.add(k)
        analyte = L.ANALYTES_BY_KEY.get(k)
        if analyte:
            picked.append(analyte)

    def sort_key(a: L.Analyte) -> Tuple[int, int]:
        group_rank = (GROUP_ORDER.index(a.group)
                      if a.group in GROUP_ORDER else len(GROUP_ORDER))
        return (group_rank, picked.index(a))

    return sorted(picked, key=sort_key)


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------
def evaluate(campaign_id: str,
             settings: SampleCampaignSettings,
             samples: Iterable[LabSample]) -> SampleCampaignSummary:
    """Judge every sample against the campaign's standard.

    The returned summary is the report's whole data source: sample columns,
    parameter rows, one evaluated cell per intersection, and the counts the
    compliance section states.
    """
    sample_list = sorted(samples, key=lambda s: (s.position, s.code))
    standard = settings.standard or "none"
    guard_band = settings.decision_rule == "guard_band"

    # Which parameters to print. The campaign's chosen list is the scope of
    # work; where none has been chosen, fall back to whatever the samples
    # actually carry, so results are never hidden because a profile is
    # missing.
    keys = list(settings.analyte_keys)
    if not keys:
        for s in sample_list:
            for r in s.results:
                if r.analyte_key not in keys:
                    keys.append(r.analyte_key)
    analytes = ordered_analytes(keys)

    # Index results for lookup, and collect names the library could not
    # resolve so a reviewer sees them rather than losing them.
    by_sample: Dict[str, Dict[str, object]] = {}
    unresolved: List[str] = []
    for s in sample_list:
        table: Dict[str, object] = {}
        for r in s.results:
            if not r.resolved or r.analyte_key not in L.ANALYTES_BY_KEY:
                label = r.reported_name or r.analyte_key
                if label and label not in unresolved:
                    unresolved.append(label)
                continue
            table[r.analyte_key] = r
        by_sample[s.id] = table

    cells: List[CellEvaluation] = []
    rows: List[Dict[str, object]] = []
    per_sample: Dict[str, Dict[str, int]] = {
        s.id: {"assessed": 0, "not_assessed": 0, "exceed": 0}
        for s in sample_list
    }
    mu_missing = False

    last_group: Optional[str] = None
    for analyte in analytes:
        if analyte.group != last_group:
            rows.append({
                "kind": "group",
                "label": GROUP_LABELS.get(analyte.group, analyte.group.title()),
            })
            last_group = analyte.group

        row_cells: List[CellEvaluation] = []
        row_unit = analyte.unit
        limit_displays: List[str] = []

        for s in sample_list:
            ctx = _merge_context(settings.default_context, s.context)
            limit = _lookup(analyte, standard, ctx)
            result = by_sample.get(s.id, {}).get(analyte.key)

            value = getattr(result, "value", None)
            below_loq = bool(getattr(result, "below_loq", False))
            if below_loq:
                # Reported as less than the quantification limit. Printed as
                # the laboratory wrote it, and never an exceedance.
                judged: Optional[float] = None
            elif value is not None and guard_band and limit.assessable:
                mu = getattr(result, "mu_percent", None)
                if mu is None:
                    mu_missing = True
                judged = _widen(value, mu, limit.direction)
            else:
                judged = value

            verdict = limit.verdict(judged)
            if below_loq and limit.assessable:
                verdict = "complies"
            # A negative concentration is not a measurement. The limit
            # refuses to judge it; the reason has to reach the report, or
            # the cell is indistinguishable from a parameter that simply has
            # no limit.
            cell_reason = limit.reason
            negative = limit.negative_reason(judged)
            if negative:
                cell_reason = negative

            unit = (getattr(result, "unit", None) or limit.unit
                    or L.default_unit(analyte, s.medium))
            row_unit = unit or row_unit
            printed_limit = limit.printed()
            if printed_limit not in limit_displays:
                limit_displays.append(printed_limit)

            cell = CellEvaluation(
                sample_id=s.id,
                sample_label=s.label or s.code,
                analyte_key=analyte.key,
                analyte_name=analyte.name,
                unit=unit,
                value=value,
                display_value=_display(result),
                below_loq=below_loq,
                limit_display=printed_limit,
                limit_value=limit.value,
                limit_low=limit.low,
                limit_high=limit.high,
                direction=limit.direction,
                verdict=verdict,
                reason=cell_reason,
                percent_of_limit=_percent_of_limit(value, limit),
                source=limit.source or None,
            )
            row_cells.append(cell)
            cells.append(cell)

            counts = per_sample[s.id]
            if result is None:
                continue
            if verdict == "not_assessed":
                counts["not_assessed"] += 1
            else:
                counts["assessed"] += 1
                if verdict == "exceeds":
                    counts["exceed"] += 1

        rows.append({
            "kind": "analyte",
            "analyte_key": analyte.key,
            "analyte_name": analyte.name,
            "unit": row_unit,
            "method": analyte.method,
            # One limit for the whole row when every sample shares a context,
            # which is the usual case; otherwise the cells carry their own.
            "limit_display": (limit_displays[0] if len(limit_displays) == 1
                              else "See sample"),
            "limit_varies": len(limit_displays) > 1,
            "cells": [c.model_dump() for c in row_cells],
        })

    evaluations: List[SampleEvaluation] = []
    total_exceedances = 0
    for s in sample_list:
        counts = per_sample[s.id]
        ctx = _merge_context(settings.default_context, s.context)
        gaps = ctx.missing_for(s.medium, standard)
        if counts["exceed"]:
            outcome = "non_compliant"
        elif counts["assessed"]:
            outcome = "compliant"
        else:
            outcome = "no_verdict"
        total_exceedances += counts["exceed"]
        evaluations.append(SampleEvaluation(
            sample_id=s.id,
            label=s.label or s.code,
            code=s.code,
            medium=s.medium,
            assessed_count=counts["assessed"],
            not_assessed_count=counts["not_assessed"],
            exceedance_count=counts["exceed"],
            outcome=outcome,
            missing_context=gaps,
        ))

    blocking = _blocking_note(standard, evaluations, guard_band, mu_missing)
    negatives = _negative_summary(cells)
    if negatives:
        blocking = f"{blocking} {negatives}" if blocking else negatives

    return SampleCampaignSummary(
        campaign_id=campaign_id,
        standard=standard,
        decision_rule=settings.decision_rule,
        samples=evaluations,
        rows=rows,
        cells=cells,
        total_exceedances=total_exceedances,
        unresolved_names=unresolved,
        blocking_note=blocking,
    )


def _negative_summary(cells: List[CellEvaluation]) -> Optional[str]:
    """Name the parameters reported as negative, so they are chased."""
    names = sorted({c.analyte_name for c in cells
                    if c.value is not None and c.value < 0
                    and c.verdict == "not_assessed"})
    if not names:
        return None
    return ("Negative values were reported for: " + ", ".join(names)
            + ". These are not physically possible concentrations and were "
              "not assessed; confirm them with the laboratory before "
              "issuing.")


def _blocking_note(standard: str, evaluations: List[SampleEvaluation],
                   guard_band: bool, mu_missing: bool) -> Optional[str]:
    """One sentence explaining why no verdict was reached, where none was.

    Printed in place of a compliance conclusion. It exists so that a report
    with no verdicts reads as a deliberate refusal rather than a bug.
    """
    if standard in UNIMPLEMENTED_STANDARDS:
        return UNIMPLEMENTED_STANDARDS[standard]
    if evaluations and all(e.outcome == "no_verdict" for e in evaluations):
        gaps = sorted({g for e in evaluations for g in e.missing_context})
        if gaps:
            return ("No compliance conclusion can be drawn because the "
                    "following has not been recorded: " + ", ".join(gaps) + ".")
        return ("No compliance conclusion can be drawn: none of the "
                "parameters determined carries a limit in the applicable "
                "standard.")
    if guard_band and mu_missing:
        return ("A guard band was selected but measurement uncertainty is "
                "missing for one or more results. Those results were "
                "compared as reported; the guard band was not applied to "
                "them.")
    return None


# ---------------------------------------------------------------------------
# Appendix table: what the limit would have been under a different land use
# ---------------------------------------------------------------------------
def land_use_comparison(analyte_keys: Sequence[str], particle_size: str,
                        depth: Optional[str] = None) -> List[Dict[str, object]]:
    """All five land-use columns for the printed parameters.

    This table is the reason the SAJCO report's wrong column would have been
    caught: it shows in one glance what the same result would have been
    judged against elsewhere.
    """
    out: List[Dict[str, object]] = []
    for analyte in ordered_analytes(analyte_keys):
        row = L.soil_limit_row(analyte.key, particle_size, depth)
        if not row:
            continue
        out.append({
            "analyte_key": analyte.key,
            "analyte_name": analyte.name,
            "unit": row["unit"],
            "values": row["values"],
        })
    return out


__all__ = [
    "GROUP_ORDER", "GROUP_LABELS", "UNIMPLEMENTED_STANDARDS",
    "ordered_analytes", "evaluate", "land_use_comparison",
]
