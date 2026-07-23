"""Phase 2 calculation engine for EcoReport AI.

Given a Campaign + its Readings + the seeded NCEC PollutantLimits, produces a
CampaignSummary containing per-pollutant statistics, per-period compliance
evaluation with the 75 % data-capture gate, meteorology summary, and wind-rose
binning.

Governing rules (locked with the user):
  1. Negative pollutant values were already nulled at ingest (per Reading
     auto_flagged_fields); this module treats them as missing.
  2. Row-level manual flagging (Reading.valid == False) invalidates EVERY
     field on that row for calculation purposes.
  3. 75 % data-capture gate per averaging period. Below that, all statistics
     and verdicts for that pollutant × period become "insufficient data —
     not reportable" (the constant INSUFFICIENT_STR).
  4. Exceedance counts are ALWAYS reported (informational). The compliance
     verdict is only rendered when the allowance window is evaluable from
     the campaign length.
  5. NO and NOx are supporting pollutants — no compliance verdict; only
     hourly descriptive stats.
  6. 8-hr rolling (CO, O3): the first 7 hours are blank; a rolling value is
     blank if fewer than 6 of the 8 window hours are valid.
  7. Prorate expected within a period (e.g. partial first/last calendar day),
     but do NOT prorate the annual reference window down to the campaign —
     that's what triggers "insufficient" for short campaigns.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from units_mdl import apply_mdl, mdl_map
from models import (
    ALL_MEASUREMENT_FIELDS,
    COMPLIANCE_POLLUTANTS,
    INSUFFICIENT_STR,
    SUPPORTING_POLLUTANTS,
    AllowanceRule,
    AllowanceWindow,
    Campaign,
    CampaignSummary,
    MeteorologySummary,
    MET_FIELDS,
    PeriodEvaluation,
    POLLUTANT_FIELDS,
    PollutantEvaluation,
    PollutantLimit,
    Reading,
    WindClassBin,
    WindDirectionRow,
    WindRoseSummary,
)


ALL_POLLUTANTS = COMPLIANCE_POLLUTANTS + SUPPORTING_POLLUTANTS

COMPASS_16 = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]

YEAR_HOURS = 8760
DAYS_30_HOURS = 30 * 24


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------
def _effective(r: Reading, field: str) -> Optional[float]:
    """Return the effective (calculation-usable) value for a field on a reading.
    Returns None when the row is manually invalidated OR the field is
    auto-flagged OR the raw value is missing."""
    if not r.valid:
        return None
    return getattr(r, field, None)


def monitoring_hours(campaign: Campaign) -> int:
    """Number of hourly slots in the monitoring window."""
    seconds = (campaign.monitoring_end - campaign.monitoring_start).total_seconds()
    return max(int(round(seconds / 3600.0)), 0)


def hour_slots(window_start: datetime, window_end: datetime) -> int:
    """Number of distinct clock hours the monitoring window touches.

    A window of 25.0 hours starting at 04:30 spans 26 clock hours (04:00
    through 05:00 the next day). Hourly statistics live in clock-hour slots,
    so capture must be measured against slots, not against elapsed hours —
    otherwise a window that starts mid-hour reports more than 100 % capture.
    """
    ws, we = _as_utc(window_start), _as_utc(window_end)
    if we <= ws:
        return 0
    first = ws.replace(minute=0, second=0, microsecond=0)
    return int(math.ceil((we - first).total_seconds() / 3600.0))


def _maxminmean(values: List[float]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if not values:
        return None, None, None
    return max(values), min(values), sum(values) / len(values)


def _compass_bin(degrees: float) -> str:
    """Convert a 0-360° bearing to a 16-point compass label."""
    deg = degrees % 360
    idx = int(round(deg / 22.5)) % 16
    return COMPASS_16[idx]


def _speed_class(ws: float, bins: List[WindClassBin]) -> Optional[str]:
    for b in bins:
        upper = b.max if b.max is not None else math.inf
        if b.min <= ws < upper:
            return b.label
    return None


# ---------------------------------------------------------------------------
# Rolling 8-hr and daily aggregation
# ---------------------------------------------------------------------------
def _as_utc(dt: datetime) -> datetime:
    """Coerce naive datetimes to UTC so aware/naive mixes never crash."""
    if dt.tzinfo is None:
        from datetime import timezone as _tz
        return dt.replace(tzinfo=_tz.utc)
    return dt


def _hour_slot(dt: datetime) -> datetime:
    return _as_utc(dt).replace(minute=0, second=0, microsecond=0)


def rolling_8h(
    readings: List[Reading],
    field: str,
    window_start: Optional[datetime] = None,
) -> List[Optional[float]]:
    """For each hourly reading, compute the 8-hr rolling mean over the CLOCK
    hours [t-7h, t] (timestamp-based, so gaps in the file do NOT silently
    stretch the window). Blank for the first 7 hours of the monitoring window
    (insufficient window — non-configurable). Blank if fewer than 6 of the 8
    clock-hour slots are valid."""
    n = len(readings)
    out: List[Optional[float]] = [None] * n
    if n == 0:
        return out
    by_hour: Dict[datetime, Optional[float]] = {}
    for r in readings:
        by_hour[_hour_slot(r.timestamp)] = _effective(r, field)
    first = _hour_slot(window_start) if window_start else _hour_slot(readings[0].timestamp)
    for i, r in enumerate(readings):
        ts = _hour_slot(r.timestamp)
        if ts - first < timedelta(hours=7):
            continue
        window = [by_hour.get(ts - timedelta(hours=j)) for j in range(8)]
        valid = [v for v in window if v is not None]
        if len(valid) < 6:
            continue
        out[i] = sum(valid) / len(valid)
    return out


def daily_means(
    readings: List[Reading],
    field: str,
    window_start: Optional[datetime] = None,
    window_end: Optional[datetime] = None,
) -> List[Tuple[date, Optional[float], int, int]]:
    """Group readings by calendar day (UTC). Return list of tuples
    (day, mean_or_None, valid_hours, expected_hours). Expected hours for a day
    are the CLOCK hours of that day intersecting the monitoring window (so
    hours missing entirely from the file still count against capture). A day's
    mean is None when its 75% capture threshold is not met."""
    by_day: Dict[date, List[Reading]] = defaultdict(list)
    for r in readings:
        by_day[_as_utc(r.timestamp).date()].append(r)
    ws = _as_utc(window_start) if window_start else None
    we = _as_utc(window_end) if window_end else None
    out: List[Tuple[date, Optional[float], int, int]] = []
    for day, rows in sorted(by_day.items()):
        if ws is not None and we is not None:
            from datetime import time as _time, timezone as _tz
            day_start = datetime.combine(day, _time.min, tzinfo=_tz.utc)
            day_end = day_start + timedelta(days=1)
            ov = (min(day_end, we) - max(day_start, ws)).total_seconds() / 3600.0
            expected = max(int(round(ov)), 0)
            # Never let the denominator drop below rows actually present.
            expected = max(expected, len(rows))
        else:
            expected = len(rows)  # fallback: rows present for this day
        if expected == 0:
            continue
        vals = [v for v in (_effective(r, field) for r in rows) if v is not None]
        if len(vals) / expected >= 0.75 and vals:
            out.append((day, sum(vals) / len(vals), len(vals), expected))
        else:
            out.append((day, None, len(vals), expected))
    return out


# ---------------------------------------------------------------------------
# Verdict determination — the heart of Rule B taxonomy.
# ---------------------------------------------------------------------------
def _verdict(
    allowance: Optional[AllowanceRule],
    monitored_hours: int,
    statistically_sufficient: bool,
    exceedance_count: int,
) -> Tuple[bool, str, str]:
    """Return (evaluable, verdict, reason).

    - If observed exceedances exceed the allowance count, that is direct
      evidence of non-compliance regardless of coverage (partial-year data
      that shows 25/24 already means the annual allowance is blown).
    - Otherwise the compliance verdict requires (a) statistical sufficiency
      of the underlying stat, AND (b) coverage of the allowance's reference
      window if that window is longer than the campaign.
    """
    if allowance is None:
        return True, "compliant" if exceedance_count == 0 else "non-compliant", ""

    count_allowed = allowance.count if allowance.count is not None else 0

    # Direct evidence of non-compliance — always evaluable.
    if exceedance_count > count_allowed:
        return True, "non-compliant", (
            f"{exceedance_count} observed exceedance(s) > allowance "
            f"({allowance.description})"
        )

    # Below-allowance count. Compliance verdict now requires enough coverage.
    if not statistically_sufficient:
        return False, INSUFFICIENT_STR, "data capture < 75% for this averaging period"

    win = allowance.window
    if win == AllowanceWindow.SINGLE_EXCEEDANCE:
        return True, "compliant", "no exceedances during monitoring window (zero-tolerance limit)"

    if win == AllowanceWindow.ANNUAL:
        if monitored_hours / YEAR_HOURS < 0.75:
            return False, INSUFFICIENT_STR, (
                f"annual allowance ({allowance.description}) requires \u226575% of {YEAR_HOURS} hours "
                f"({monitored_hours} hours monitored)"
            )
        return True, "compliant", (
            f"{exceedance_count} exceedance(s) \u2264 allowance {allowance.description}"
        )

    if win == AllowanceWindow.DAYS_30:
        if monitored_hours / DAYS_30_HOURS < 0.75:
            return False, INSUFFICIENT_STR, (
                f"30-day allowance ({allowance.description}) requires \u226575% of "
                f"{DAYS_30_HOURS} hours ({monitored_hours} hours monitored)"
            )
        return True, "compliant", (
            f"{exceedance_count} exceedance(s) \u2264 allowance {allowance.description}"
        )

    if win == AllowanceWindow.ANNUAL_MEAN:
        # Handled explicitly by the caller in the annual-period branch.
        return False, INSUFFICIENT_STR, "annual mean requires \u226575% annual data capture"

    return False, INSUFFICIENT_STR, "unknown allowance window"


# ---------------------------------------------------------------------------
# Per-period evaluators
# ---------------------------------------------------------------------------
def _evaluate_hourly(
    limit: PollutantLimit,
    readings: List[Reading],
    monitored_hours: int,
    slots: Optional[int] = None,
) -> PeriodEvaluation:
    field = limit.pollutant
    vals = [v for v in (_effective(r, field) for r in readings) if v is not None]
    expected = slots or monitored_hours
    capture_pct = min((len(vals) / expected * 100.0) if expected else 0.0, 100.0)
    sufficient = capture_pct >= 75.0
    max_v, min_v, mean_v = _maxminmean(vals) if sufficient else (None, None, None)
    exceed = sum(1 for v in vals if v > limit.limit_ugm3)
    evaluable, verdict, reason = _verdict(limit.allowance, monitored_hours, sufficient, exceed)
    return PeriodEvaluation(
        averaging_period=limit.averaging_period,
        limit_ugm3=limit.limit_ugm3,
        allowance_description=(limit.allowance.description if limit.allowance
                               else (limit.allowable_exceedances or "")),
        expected_readings=expected,
        valid_readings=len(vals),
        capture_pct=capture_pct,
        sufficient=sufficient,
        max_value=max_v,
        min_value=min_v,
        mean_value=mean_v,
        exceedance_count=exceed,
        exceedance_evaluable=evaluable,
        verdict=verdict,
        verdict_reason=reason,
    )


def _evaluate_8h_rolling(
    limit: PollutantLimit,
    readings: List[Reading],
    monitored_hours: int,
    window_start: Optional[datetime] = None,
) -> PeriodEvaluation:
    field = limit.pollutant
    rolling = rolling_8h(readings, field, window_start=window_start)
    valid_rolling = [v for v in rolling if v is not None]
    expected = max(monitored_hours - 7, 0)
    capture_pct = (len(valid_rolling) / expected * 100.0) if expected else 0.0
    sufficient = capture_pct >= 75.0
    max_v, min_v, mean_v = _maxminmean(valid_rolling) if sufficient else (None, None, None)
    exceed = sum(1 for v in valid_rolling if v > limit.limit_ugm3)
    evaluable, verdict, reason = _verdict(limit.allowance, monitored_hours, sufficient, exceed)
    return PeriodEvaluation(
        averaging_period=limit.averaging_period,
        limit_ugm3=limit.limit_ugm3,
        allowance_description=(limit.allowance.description if limit.allowance
                               else (limit.allowable_exceedances or "")),
        expected_readings=expected,
        valid_readings=len(valid_rolling),
        capture_pct=capture_pct,
        sufficient=sufficient,
        max_value=max_v,
        min_value=min_v,
        mean_value=mean_v,
        exceedance_count=exceed,
        exceedance_evaluable=evaluable,
        verdict=verdict,
        verdict_reason=reason,
    )


def _evaluate_daily(
    limit: PollutantLimit,
    readings: List[Reading],
    monitored_hours: int,
    window_start: Optional[datetime] = None,
    window_end: Optional[datetime] = None,
) -> PeriodEvaluation:
    field = limit.pollutant
    daily = daily_means(readings, field, window_start=window_start, window_end=window_end)
    valid_days = [d for d in daily if d[1] is not None]
    expected = len(daily)  # number of calendar days touched by the monitoring window
    capture_pct = (len(valid_days) / expected * 100.0) if expected else 0.0
    sufficient = capture_pct >= 75.0
    day_vals = [d[1] for d in valid_days]
    max_v, min_v, mean_v = _maxminmean(day_vals) if sufficient else (None, None, None)
    exceed = sum(1 for v in day_vals if v > limit.limit_ugm3)
    evaluable, verdict, reason = _verdict(limit.allowance, monitored_hours, sufficient, exceed)
    return PeriodEvaluation(
        averaging_period=limit.averaging_period,
        limit_ugm3=limit.limit_ugm3,
        allowance_description=(limit.allowance.description if limit.allowance
                               else (limit.allowable_exceedances or "")),
        expected_readings=expected,
        valid_readings=len(valid_days),
        capture_pct=capture_pct,
        sufficient=sufficient,
        max_value=max_v,
        min_value=min_v,
        mean_value=mean_v,
        exceedance_count=exceed,
        exceedance_evaluable=evaluable,
        verdict=verdict,
        verdict_reason=reason,
    )


def _evaluate_annual(
    limit: PollutantLimit,
    readings: List[Reading],
    monitored_hours: int,
) -> PeriodEvaluation:
    """Annual arithmetic mean vs limit. Requires >=75% of 8760 hours to be
    valid → for any short campaign this returns "insufficient" per the rule
    locked with the user (edge-case #1: annual row always shown)."""
    field = limit.pollutant
    vals = [v for v in (_effective(r, field) for r in readings) if v is not None]
    expected = YEAR_HOURS  # deliberately NOT prorated for annual
    capture_pct = (len(vals) / expected * 100.0)
    sufficient = capture_pct >= 75.0
    mean_v = (sum(vals) / len(vals)) if (sufficient and vals) else None
    # For annual mean the "exceedance count" is 1 if mean > limit else 0.
    exceed = 1 if (mean_v is not None and mean_v > limit.limit_ugm3) else 0
    if sufficient and mean_v is not None:
        verdict = "compliant" if exceed == 0 else "non-compliant"
        reason = (
            f"annual mean {mean_v:.2f} \u00b5g/m\u00b3 \u2264 {limit.limit_ugm3}"
            if exceed == 0
            else f"annual mean {mean_v:.2f} \u00b5g/m\u00b3 > {limit.limit_ugm3}"
        )
        evaluable = True
    else:
        verdict = INSUFFICIENT_STR
        reason = (
            f"annual mean requires \u226575% of {YEAR_HOURS} hours "
            f"({len(vals)} valid of {expected} expected)"
        )
        evaluable = False
    return PeriodEvaluation(
        averaging_period=limit.averaging_period,
        limit_ugm3=limit.limit_ugm3,
        allowance_description=(limit.allowance.description if limit.allowance
                               else (limit.allowable_exceedances or "")),
        expected_readings=expected,
        valid_readings=len(vals),
        capture_pct=capture_pct,
        sufficient=sufficient,
        max_value=None,
        min_value=None,
        mean_value=mean_v,
        exceedance_count=exceed,
        exceedance_evaluable=evaluable,
        verdict=verdict,
        verdict_reason=reason,
    )


def _evaluate_limit(
    limit: PollutantLimit,
    readings: List[Reading],
    monitored_hours: int,
    window_start: Optional[datetime] = None,
    window_end: Optional[datetime] = None,
) -> PeriodEvaluation:
    hours = limit.averaging_period_hours
    if hours == 1:
        slots = (hour_slots(window_start, window_end)
                 if (window_start and window_end) else None)
        return _evaluate_hourly(limit, readings, monitored_hours, slots=slots)
    if hours == 8:
        return _evaluate_8h_rolling(limit, readings, monitored_hours, window_start=window_start)
    if hours == 24:
        return _evaluate_daily(limit, readings, monitored_hours,
                               window_start=window_start, window_end=window_end)
    return _evaluate_annual(limit, readings, monitored_hours)


# ---------------------------------------------------------------------------
# Per-pollutant + meteorology + wind rose
# ---------------------------------------------------------------------------
def _pollutant_evaluation(
    pollutant: str,
    readings: List[Reading],
    limits_for_pollutant: List[PollutantLimit],
    monitored_hours: int,
    window_start: Optional[datetime] = None,
    window_end: Optional[datetime] = None,
    mdl: Optional[float] = None,
    slots: Optional[int] = None,
) -> PollutantEvaluation:
    is_supporting = pollutant in SUPPORTING_POLLUTANTS

    # Below the instrument's detection limit a reading is noise, not a
    # measurement. USEPA practice is to substitute MDL/2 in calculations and
    # to report such values as "<MDL" rather than as raw digits.
    below_mdl_count = 0
    if mdl and mdl > 0:
        subbed: List[Reading] = []
        for r in readings:
            v = _effective(r, pollutant)
            nv, was_below = apply_mdl(v, mdl)
            if was_below:
                below_mdl_count += 1
                r = r.model_copy(update={pollutant: nv})
            subbed.append(r)
        readings = subbed

    # Hourly stats always computed (also used for supporting pollutants).
    vals = [v for v in (_effective(r, pollutant) for r in readings) if v is not None]
    expected = slots or monitored_hours
    capture_pct = min((len(vals) / expected * 100.0) if expected else 0.0, 100.0)
    hourly_sufficient = capture_pct >= 75.0
    h_max, h_min, h_mean = _maxminmean(vals) if hourly_sufficient else (None, None, None)

    r8_max = r8_min = r8_mean = None
    r8_valid_count = 0
    r8_expected = 0
    # 8-hour rolling only for CO and O3
    if pollutant in ("CO", "O3"):
        rolling = rolling_8h(readings, pollutant, window_start=window_start)
        valid_rolling = [v for v in rolling if v is not None]
        r8_expected = max(monitored_hours - 7, 0)
        r8_valid_count = len(valid_rolling)
        r8_capture = (len(valid_rolling) / r8_expected * 100.0) if r8_expected else 0.0
        if r8_capture >= 75.0:
            r8_max, r8_min, r8_mean = _maxminmean(valid_rolling)

    # Compliance evaluations against every applicable NCEC limit
    period_evals = []
    if not is_supporting:
        for lim in sorted(
            limits_for_pollutant,
            key=lambda l: (
                _period_sort_key(l.averaging_period_hours),
                l.averaging_period,
            ),
        ):
            period_evals.append(_evaluate_limit(
                lim, readings, monitored_hours,
                window_start=window_start, window_end=window_end,
            ))

    _extra = {"below_mdl_count": below_mdl_count, "mdl_ugm3": mdl} \
        if (mdl and mdl > 0) else {}
    return PollutantEvaluation(
        pollutant=pollutant,
        is_supporting=is_supporting,
        hourly_capture_pct=capture_pct,
        hourly_valid_count=len(vals),
        hourly_expected_count=expected,
        hourly_max=h_max,
        hourly_min=h_min,
        hourly_mean=h_mean,
        rolling_8h_max=r8_max,
        rolling_8h_min=r8_min,
        rolling_8h_mean=r8_mean,
        rolling_8h_valid_count=r8_valid_count,
        rolling_8h_expected_count=r8_expected,
        period_evaluations=period_evals,
        **_extra,
    )


def _period_sort_key(h: Optional[float]) -> int:
    order = {1: 0, 8: 1, 24: 2}
    return order.get(int(h) if h else -1, 3)  # None (annual) sorts last


def _meteorology_summary(readings: List[Reading], monitored_hours: int,
                         slots: Optional[int] = None) -> MeteorologySummary:
    denom = slots or monitored_hours

    def stats(field: str):
        vals = [v for v in (_effective(r, field) for r in readings) if v is not None]
        cap = min((len(vals) / denom * 100.0) if denom else 0.0, 100.0)
        mx, mn, mean = _maxminmean(vals)
        return cap, mx, mn, mean, vals

    t_cap, t_max, t_min, t_mean, _ = stats("Temp")
    rh_cap, rh_max, rh_min, rh_mean, _ = stats("RH")
    p_cap, p_max, p_min, p_mean, _ = stats("Pressure")
    ws_cap, ws_max, ws_min, ws_mean, _ = stats("WindSpeed")
    wd_vals = [v for v in (_effective(r, "WindDirection") for r in readings) if v is not None]
    wd_cap = min((len(wd_vals) / denom * 100.0) if denom else 0.0, 100.0)
    prevailing = None
    if wd_vals:
        counts = Counter(_compass_bin(d) for d in wd_vals)
        prevailing = counts.most_common(1)[0][0]

    return MeteorologySummary(
        monitoring_hours=monitored_hours,
        temp_capture_pct=t_cap, temp_max=t_max, temp_min=t_min, temp_mean=t_mean,
        rh_capture_pct=rh_cap, rh_max=rh_max, rh_min=rh_min, rh_mean=rh_mean,
        pressure_capture_pct=p_cap, pressure_max=p_max, pressure_min=p_min, pressure_mean=p_mean,
        wind_speed_capture_pct=ws_cap, wind_speed_max=ws_max, wind_speed_min=ws_min,
        wind_speed_mean=ws_mean,
        wind_direction_capture_pct=wd_cap,
        prevailing_wind_direction=prevailing,
    )


def _wind_rose_summary(
    readings: List[Reading],
    bins: List[WindClassBin],
    monitored_hours: int,
) -> WindRoseSummary:
    valid_pairs: List[Tuple[float, float]] = []
    for r in readings:
        ws = _effective(r, "WindSpeed")
        wd = _effective(r, "WindDirection")
        if ws is not None and wd is not None:
            valid_pairs.append((ws, wd))

    total_valid = len(valid_pairs)
    class_totals: Dict[str, int] = {b.label: 0 for b in bins}
    direction_rows: List[WindDirectionRow] = []

    for dir_label in COMPASS_16:
        cbc: Dict[str, int] = {b.label: 0 for b in bins}
        for ws, wd in valid_pairs:
            if _compass_bin(wd) != dir_label:
                continue
            sc = _speed_class(ws, bins)
            if sc:
                cbc[sc] += 1
                class_totals[sc] += 1
        total = sum(cbc.values())
        freq_pct = (total / total_valid * 100.0) if total_valid else 0.0
        direction_rows.append(WindDirectionRow(
            direction=dir_label,
            counts_by_class=cbc,
            total=total,
            frequency_pct=freq_pct,
        ))

    calm_bin = next(
        (b for b in bins if b.label.strip().lower() in ("calm", "calms")),
        None,
    )
    calms_count = class_totals.get(calm_bin.label, 0) if calm_bin else 0
    calms_pct = (calms_count / total_valid * 100.0) if total_valid else 0.0
    class_frequency_pct = {
        k: ((v / total_valid * 100.0) if total_valid else 0.0)
        for k, v in class_totals.items()
    }
    prevailing = (
        max(direction_rows, key=lambda r: r.total).direction
        if (direction_rows and total_valid)
        else None
    )
    mean_ws = (sum(ws for ws, _ in valid_pairs) / total_valid) if total_valid else None

    return WindRoseSummary(
        bins=bins,
        direction_rows=direction_rows,
        class_totals=class_totals,
        class_frequency_pct=class_frequency_pct,
        total_valid=total_valid,
        total_hours=monitored_hours,
        calms_count=calms_count,
        calms_pct=calms_pct,
        prevailing_direction=prevailing,
        mean_wind_speed=mean_ws,
    )


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def _to_hourly(readings: List[Reading]) -> List[Reading]:
    """Collapse sub-hourly data to one reading per clock hour.

    Vendor exports are sometimes 30-, 15- or 5-minute data. Every statistic in
    this report is defined on HOURLY values (NCEC 1-hour limits, 8-hour rolling
    means, daily means, data-capture %), so sub-hourly rows must be averaged
    into their clock hour first — otherwise capture can exceed 100% and the
    "hourly maximum" would really be a short-interval maximum.

    Only valid values contribute to an hourly mean; an hour with no valid value
    for a field yields None for that field. Data already at hourly resolution
    passes through unchanged.
    """
    if len(readings) < 2:
        return readings
    stamps = sorted(_as_utc(r.timestamp) for r in readings)
    gaps = [(b - a).total_seconds() for a, b in zip(stamps, stamps[1:])
            if (b - a).total_seconds() > 0]
    if not gaps:
        return readings
    gaps.sort()
    median_gap = gaps[len(gaps) // 2]
    if median_gap >= 3000:          # ~50 min or more -> already hourly
        return readings

    buckets: Dict[datetime, List[Reading]] = defaultdict(list)
    for r in readings:
        buckets[_as_utc(r.timestamp).replace(minute=0, second=0,
                                             microsecond=0)].append(r)

    fields = ALL_MEASUREMENT_FIELDS if "ALL_MEASUREMENT_FIELDS" in globals() \
        else [f for f in Reading.model_fields
              if f not in ("id", "campaign_id", "timestamp", "valid",
                           "invalidation_reason", "auto_flagged_fields",
                           "created_at")]

    out: List[Reading] = []
    for hour in sorted(buckets):
        rows = buckets[hour]
        data: Dict[str, Optional[float]] = {}
        for f in fields:
            vals = [v for v in (_effective(r, f) for r in rows) if v is not None]
            if f == "WindDirection" and vals:
                # circular mean, so 350° and 10° average to 0°, not 180°
                rad = [math.radians(v) for v in vals]
                ang = math.degrees(math.atan2(
                    sum(math.sin(a) for a in rad) / len(rad),
                    sum(math.cos(a) for a in rad) / len(rad)))
                data[f] = round(ang % 360.0, 1)
            else:
                data[f] = round(sum(vals) / len(vals), 3) if vals else None
        out.append(Reading(
            campaign_id=rows[0].campaign_id, timestamp=hour, valid=True,
            auto_flagged_fields=sorted({f for r in rows
                                        for f in (r.auto_flagged_fields or [])}),
            **data))
    return out


def build_campaign_summary(
    campaign: Campaign,
    readings: List[Reading],
    limits: List[PollutantLimit],
) -> CampaignSummary:
    """Compute and return the CampaignSummary for the given inputs.
    Callers are responsible for fetching readings (sorted by timestamp asc)
    and PollutantLimits from the DB."""
    m_hours = monitoring_hours(campaign)

    # Only readings inside [monitoring_start, monitoring_end) count toward
    # statistics and capture %. Out-of-window rows (e.g. a trailing 00:00
    # endpoint row, or pre-campaign warm-up hours) are excluded here so
    # capture can never exceed 100%.
    w_start = _as_utc(campaign.monitoring_start)
    w_end = _as_utc(campaign.monitoring_end)
    readings = [r for r in readings if w_start <= _as_utc(r.timestamp) < w_end]

    # Collapse sub-hourly exports (30/15/5-minute data) into hourly means so
    # every statistic below is a true hourly value and capture % is bounded.
    readings = _to_hourly(readings)
    slots = hour_slots(w_start, w_end)

    # Group limits by pollutant for fast lookup
    limits_by_pol: Dict[str, List[PollutantLimit]] = defaultdict(list)
    for lim in limits:
        limits_by_pol[lim.pollutant].append(lim)

    mdls = mdl_map(getattr(campaign, "instruments", None))

    pollutants: List[PollutantEvaluation] = []
    for pol in ALL_POLLUTANTS:
        pollutants.append(_pollutant_evaluation(
            pol, readings, limits_by_pol.get(pol, []), m_hours,
            window_start=w_start, window_end=w_end, mdl=mdls.get(pol),
            slots=slots,
        ))

    met = _meteorology_summary(readings, m_hours, slots=slots)
    wr = _wind_rose_summary(readings, campaign.wind_rose_bins, slots)

    manually_flagged = sum(1 for r in readings if not r.valid)
    auto_flagged = sum(1 for r in readings if r.auto_flagged_fields)

    # Overall hourly capture: mean across compliance-tracked pollutants.
    caps = [p.hourly_capture_pct for p in pollutants if p.pollutant in COMPLIANCE_POLLUTANTS]
    overall_cap = (sum(caps) / len(caps)) if caps else 0.0

    return CampaignSummary(
        campaign_id=campaign.id,
        monitoring_start=campaign.monitoring_start,
        monitoring_end=campaign.monitoring_end,
        monitoring_hours=m_hours,
        total_readings=len(readings),
        manually_flagged_readings=manually_flagged,
        auto_flagged_readings=auto_flagged,
        overall_hourly_capture_pct=overall_cap,
        pollutants=pollutants,
        meteorology=met,
        wind_rose=wr,
    )
