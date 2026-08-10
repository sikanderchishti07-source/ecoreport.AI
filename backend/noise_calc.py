# -*- coding: utf-8 -*-
"""Acoustic statistics for noise campaigns.

Decibels are logarithmic, so they must never be averaged arithmetically:
every equivalent level here is an energy average,

    LAeq = 10 · log10( mean( 10^(Li/10) ) )

This matters in practice. BSA's manual Dragon Ball report arithmetic-averaged
the day period and understated L_Day by 1.4 dB; its other statistics were
energy-averaged correctly. This module reproduces every correctly-computed
figure in that report to two decimal places (LAeq 60.08, LA10 61.20, LA50
58.70, LA90 57.00, Lmax 77.50, Lmin 55.20) and computes L_Day the right way.

Percentile convention: LA10 is the level exceeded 10% of the time — the 90th
percentile of the record — and LA90 the level exceeded 90% of the time. The
day period is taken from the campaign (default 07:00–20:00) using the naive
local timestamps, per the locked rule that KSA time is never stamped UTC.

Day period. The Executive Regulation for Noise (Royal Decree M/165,
Article 1 — Definitions) defines daytime as the period between 7.00 am and
8.00 pm, and night-time as 8.00 pm to 7.00 am. This module previously
defaulted the day period to 07:00–19:00, which placed the 19:00–20:00 hour
in the night average and judged it against a limit 10 dB tighter than the
one that applies. The default is now the regulation's own window.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

# The regulation's day period. Article 1 defines these; they are not a matter
# of professional judgement, so they are named here rather than left as bare
# numbers in a signature.
REGULATORY_DAY_START = 7
REGULATORY_DAY_END = 20


def laeq(levels: Sequence[float]) -> Optional[float]:
    """Energy-averaged equivalent level of a set of dB values."""
    vals = [v for v in levels if v is not None]
    if not vals:
        return None
    return 10.0 * math.log10(sum(10 ** (v / 10.0) for v in vals) / len(vals))


def percentile(levels: Sequence[float], pct: float) -> Optional[float]:
    """Linear-interpolated percentile, matching numpy's default — which is
    what the verification against the manual report was done with."""
    vals = sorted(v for v in levels if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * pct / 100.0
    f = math.floor(k)
    c = min(f + 1, len(vals) - 1)
    return vals[f] + (vals[c] - vals[f]) * (k - f)


@dataclass
class HourPoint:
    hour: datetime               # start of the hour, naive local
    laeq: float
    count: int
    is_day: bool


@dataclass
class NoiseSummary:
    total_records: int
    valid_records: int
    invalid_records: int
    expected_records: int        # one per minute across the window
    data_capture_pct: float

    laeq_t: Optional[float]      # whole survey
    l_day: Optional[float]
    l_night: Optional[float]
    la10: Optional[float]
    la50: Optional[float]
    la90: Optional[float]
    lmax: Optional[float]
    lmin: Optional[float]
    lmax_at: Optional[datetime]

    day_start_hour: int
    day_end_hour: int
    day_records: int
    night_records: int
    # How often the meter logged, taken from the data itself. Reports must
    # describe the measurement they actually made — "one-minute intervals"
    # was hardcoded and became untrue the moment a per-second logger was
    # used.
    interval_seconds: float = 60.0

    hourly: List[HourPoint] = field(default_factory=list)
    # sorted levels + exceedance percentages, for the distribution chart
    dist_levels: List[float] = field(default_factory=list)
    dist_exceed: List[float] = field(default_factory=list)


def _in_day(ts: datetime, start_h: int, end_h: int) -> bool:
    """True when the timestamp falls in the day period. Handles a day window
    that crosses midnight (end <= start), although the regulation's does not."""
    h = ts.hour
    if start_h < end_h:
        return start_h <= h < end_h
    return h >= start_h or h < end_h


def _as_dt(v) -> datetime:
    """Mongo returns timestamps as ISO strings; the engine needs datetimes.
    Any timezone marker is stripped — the locked rule is that timestamps are
    naive local (KSA) time, and comparing an aware value against the naive
    campaign window would raise just as loudly as comparing a string did."""
    if isinstance(v, datetime):
        return v.replace(tzinfo=None) if v.tzinfo else v
    return datetime.fromisoformat(str(v).replace("Z", "+00:00")) \
        .replace(tzinfo=None)


def coerce_timestamps(readings: List[dict]) -> List[dict]:
    """Normalise every reading's timestamp in place. Mutating the dicts means
    the same list handed onward to the charts already carries datetimes."""
    for r in readings:
        r["timestamp"] = _as_dt(r["timestamp"])
    return readings


def build_noise_summary(readings: List[dict],
                        window_start: datetime,
                        window_end: datetime,
                        day_start_hour: int = REGULATORY_DAY_START,
                        day_end_hour: int = REGULATORY_DAY_END) -> NoiseSummary:
    """Statistics over the valid readings inside the monitoring window.

    ``readings`` are dicts with at least ``timestamp``, ``laeq`` and
    ``valid`` — the shape they take straight from Mongo, where timestamps
    arrive as ISO strings and are normalised here.
    """
    readings = coerce_timestamps(readings)
    window_start = _as_dt(window_start)
    window_end = _as_dt(window_end)
    in_window = [r for r in readings
                 if window_start <= r["timestamp"] < window_end]
    valid = [r for r in in_window if r.get("valid", True)
             and r.get("laeq") is not None]

    levels = [float(r["laeq"]) for r in valid]
    day_lv, night_lv = [], []
    for r in valid:
        (day_lv if _in_day(r["timestamp"], day_start_hour, day_end_hour)
         else night_lv).append(float(r["laeq"]))

    lmax_at = None
    if valid:
        peak = max(valid, key=lambda r: r["laeq"])
        lmax_at = peak["timestamp"]

    # hourly LAeq for the profile chart
    buckets: Dict[datetime, List[float]] = defaultdict(list)
    for r in valid:
        buckets[r["timestamp"].replace(minute=0, second=0,
                                       microsecond=0)].append(float(r["laeq"]))
    hourly = [HourPoint(hour=k, laeq=laeq(v), count=len(v),
                        is_day=_in_day(k, day_start_hour, day_end_hour))
              for k, v in sorted(buckets.items())]

    # exceedance distribution (downsampled: the chart needs a curve, not
    # every one of tens of thousands of points)
    dist_levels: List[float] = []
    dist_exceed: List[float] = []
    if levels:
        sv = sorted(levels)
        n = len(sv)
        step = max(1, n // 400)
        for i in range(0, n, step):
            dist_levels.append(sv[i])
            dist_exceed.append(100.0 * (1 - (i + 1) / n))

    # The logging interval is whatever the meter used — one reading a minute
    # on some instruments, one a second on others. Assume nothing: take the
    # median gap between consecutive readings and derive the expected count
    # from it, so data capture reads correctly for any logger.
    step_s = 60.0
    if len(valid) >= 3:
        stamps = sorted(r["timestamp"] for r in valid)
        gaps = sorted((b - a).total_seconds()
                      for a, b in zip(stamps, stamps[1:]) if b > a)
        if gaps:
            step_s = max(1.0, gaps[len(gaps) // 2])
    expected = max(1, int((window_end - window_start).total_seconds()
                          // step_s))
    return NoiseSummary(
        interval_seconds=step_s,
        total_records=len(in_window),
        valid_records=len(valid),
        invalid_records=len(in_window) - len(valid),
        expected_records=expected,
        data_capture_pct=round(100.0 * len(valid) / expected, 1),
        laeq_t=laeq(levels),
        l_day=laeq(day_lv),
        l_night=laeq(night_lv),
        la10=percentile(levels, 90),
        la50=percentile(levels, 50),
        la90=percentile(levels, 10),
        lmax=max(levels) if levels else None,
        lmin=min(levels) if levels else None,
        lmax_at=lmax_at,
        day_start_hour=day_start_hour,
        day_end_hour=day_end_hour,
        day_records=len(day_lv),
        night_records=len(night_lv),
        hourly=hourly,
        dist_levels=dist_levels,
        dist_exceed=dist_exceed,
    )


# ---------------------------------------------------------------------------
# NCEC noise limits — Executive Regulation for Noise, Royal Decree M/165
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class NoiseLimit:
    code: str
    label: str
    day_db: Optional[float]
    night_db: Optional[float]
    # A short name that reads correctly inside a sentence. The full label is
    # a table caption and does not.
    short: str = ""


NOISE_LIMITS: Dict[str, NoiseLimit] = {
    # Article 4, Table (1)
    "A": NoiseLimit("A", "Category A — low-density residential, tourist "
                         "attractions, recreational parks, and the "
                         "surroundings of hospitals, schools, elder care "
                         "centres, nurseries and environmentally sensitive "
                         "areas", 50, 40, "Category A"),
    "B": NoiseLimit("B", "Category B — medium-density residential areas",
                    55, 45, "Category B"),
    "C": NoiseLimit("C", "Category C — high-density residential areas and "
                         "areas of both residential and commercial activity",
                    60, 50, "Category C"),
    "D": NoiseLimit("D", "Category D — commercial areas, including warehouses "
                         "and financial centres", 65, 55, "Category D"),
    # Article 5, Table (2)
    "roadside": NoiseLimit("roadside", "Roadside — main roads and highways",
                           70, 65, "a roadside area"),
    # Article 6, Table (3)
    "industrial": NoiseLimit("industrial",
                             "Industrial zones, including the outdoor "
                             "premises of activities", 70, 65, "an industrial zone"),
    # Article 7 — a construction work site has NO standard of its own. It
    # takes the standard of the zone it sits in (Article 4, 5 or 6) with the
    # Table (4) correction added, and the correction is permitted only
    # between 07:00 and 18:00. This entry therefore carries no numbers: a
    # construction campaign cannot be judged until the surrounding zone and
    # the duration of activities are known. It previously carried 70/65 —
    # the roadside figures — which judged construction inside a Category A
    # residential area against a limit 20 dB too lenient.
    "construction": NoiseLimit("construction",
                               "Construction work site — the standard of the "
                               "surrounding zone with the Article 7 "
                               "correction applied", None, None),
    "tbd": NoiseLimit("tbd", "To be determined by the consultant",
                      None, None),
}

# The zones a construction site can sit in. Construction is not itself a
# zone, so it cannot be its own base.
BASE_ZONE_CODES: Tuple[str, ...] = ("A", "B", "C", "D", "roadside",
                                    "industrial")

# Table (4) — corrections to the allowed noise levels at construction work
# sites, by the duration of construction activities. "Over 8 hours" carries
# no correction at all: a site working a full day is held to the ordinary
# limit of its zone.
CONSTRUCTION_CORRECTIONS: List[Tuple[str, int]] = [
    ("Up to 2.5 hours", 10),
    ("From 2.5 to 8 hours", 5),
    ("Over 8 hours", 0),
]

# Article 7(1): the exceedance is permitted in construction work sites from
# 7.00 am to 6.00 pm. Outside those hours no correction applies.
CONSTRUCTION_START_HOUR = 7
CONSTRUCTION_END_HOUR = 18


def construction_correction(activity_hours: Optional[float]) -> Optional[int]:
    """Table (4) correction in dB for a stated duration of construction
    activity. Returns None when the duration is unknown — the caller must
    then decline to judge rather than assume the most generous band."""
    if activity_hours is None:
        return None
    try:
        h = float(activity_hours)
    except (TypeError, ValueError):
        return None
    if h <= 0:
        return None
    if h <= 2.5:
        return 10
    if h <= 8:
        return 5
    return 0


def construction_band(activity_hours: Optional[float]) -> Optional[str]:
    """The Table (4) row label matching a stated duration."""
    c = construction_correction(activity_hours)
    if c is None:
        return None
    for label, db in CONSTRUCTION_CORRECTIONS:
        if db == c:
            return label
    return None


@dataclass
class NoiseVerdict:
    period: str                  # "day" | "night"
    measured: float
    limit: float
    margin: float                # measured - limit; negative is under
    status: str                  # "ok" | "over"
    text: str


def applicable_limits(category: str,
                      base_category: Optional[str] = None,
                      activity_hours: Optional[float] = None
                      ) -> Tuple[Optional[float], Optional[float], str]:
    """The day and night limits that actually apply, with a sentence stating
    where they come from.

    For every category except construction this is simply the table value.
    For construction it is the surrounding zone's value with the Article 7
    correction added to the day figure only — the regulation grants no
    night-time allowance to construction work.
    """
    limit = NOISE_LIMITS.get(category)
    if limit is None:
        return None, None, ""
    if category != "construction":
        return limit.day_db, limit.night_db, ""

    base = NOISE_LIMITS.get(base_category) if base_category else None
    if base is None or base.day_db is None \
            or base_category not in BASE_ZONE_CODES:
        return None, None, ""
    correction = construction_correction(activity_hours)
    if correction is None:
        return None, None, ""
    band = construction_band(activity_hours)
    zone = base.short or base.label
    basis = (
        f"The site lies within {zone}, for which the standards "
        f"are {base.day_db:.0f} dB(A) by day and {base.night_db:.0f} dB(A) at "
        f"night. Article (7) of the Executive Regulation permits construction "
        f"work sites to exceed that standard between 07:00 and 18:00 by the "
        f"correction value of Table (4); for activities lasting "
        f"{band.lower()} the correction is +{correction} dB(A), giving a "
        f"corrected day-time limit of {base.day_db + correction:.0f} dB(A). "
        f"No correction is permitted at night."
    )
    return base.day_db + correction, base.night_db, basis


def assess(summary: NoiseSummary,
           category: str,
           base_category: Optional[str] = None,
           activity_hours: Optional[float] = None) -> List[NoiseVerdict]:
    """Measured day and night levels against the campaign's category.

    An empty list means no judgement is made — the "to be determined"
    posture, in which the report states the levels against every category
    and leaves the assessment to the consultant.

    A construction campaign also returns an empty list unless both the
    surrounding zone (``base_category``) and the duration of construction
    activities (``activity_hours``) are known, because Article 7 defines the
    construction limit only in terms of those two facts. Printing no verdict
    is the correct outcome; printing one against a guessed limit is not.
    """
    day_limit, night_limit, basis = applicable_limits(
        category, base_category, activity_hours)
    if day_limit is None:
        return []

    out: List[NoiseVerdict] = []
    for period, measured, lim in (("day", summary.l_day, day_limit),
                                  ("night", summary.l_night, night_limit)):
        if measured is None or lim is None:
            continue
        margin = measured - lim
        status = "ok" if margin <= 0 else "over"
        name = "Day-time L Day" if period == "day" else "Night-time L Night"
        if status == "ok":
            text = (f"{name} of {measured:.1f} dB(A) against a limit of "
                    f"{lim:.0f} dB(A) — {abs(margin):.1f} dB below the "
                    f"permissible level.")
        else:
            text = (f"{name} of {measured:.1f} dB(A) against a limit of "
                    f"{lim:.0f} dB(A) — {margin:.1f} dB above the "
                    f"permissible level.")
        # A construction day verdict must say where its limit came from, and
        # must not let the reader assume the correction covered the whole
        # day period when the survey ran past 18:00.
        if category == "construction" and period == "day":
            text = f"{text} {basis}"
            if summary.day_end_hour > CONSTRUCTION_END_HOUR:
                text = (f"{text} The day period extends to "
                        f"{summary.day_end_hour:02d}:00, beyond the 18:00 "
                        f"limit of the Article (7) allowance; levels measured "
                        f"after 18:00 are included in L Day but carry no "
                        f"correction.")
        out.append(NoiseVerdict(period=period, measured=measured, limit=lim,
                                margin=margin, status=status, text=text))
    return out
