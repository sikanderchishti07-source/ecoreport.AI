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
day period is taken from the campaign (default 07:00–19:00) using the naive
local timestamps, per the locked rule that KSA time is never stamped UTC.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple


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


def build_noise_summary(readings: List[dict],
                        window_start: datetime,
                        window_end: datetime,
                        day_start_hour: int = 7,
                        day_end_hour: int = 19) -> NoiseSummary:
    """Statistics over the valid readings inside the monitoring window.

    ``readings`` are dicts with at least ``timestamp`` (naive local datetime),
    ``laeq`` and ``valid`` — the shape they take straight from Mongo.
    """
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

    expected = max(1, int((window_end - window_start).total_seconds() // 60))
    return NoiseSummary(
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
# NCEC noise limits — Implementing Regulations for Noise, Royal Decree M/165
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class NoiseLimit:
    code: str
    label: str
    day_db: Optional[float]
    night_db: Optional[float]


NOISE_LIMITS: Dict[str, NoiseLimit] = {
    "A": NoiseLimit("A", "Category A — sensitive zones (hospitals, schools)",
                    50, 40),
    "B": NoiseLimit("B", "Category B — residential areas", 55, 45),
    "C": NoiseLimit("C", "Category C — mixed residential and commercial",
                    60, 50),
    "D": NoiseLimit("D", "Category D — commercial and business districts",
                    65, 55),
    "roadside": NoiseLimit("roadside", "Roadside — main roads and highways",
                           70, 65),
    "industrial": NoiseLimit("industrial", "Industrial zones", 70, 65),
    # Construction sites take the roadside base with the correction of
    # Table 8 applied per activity duration; the correction is stated in the
    # report rather than silently added to a limit.
    "construction": NoiseLimit("construction",
                               "Construction work site (corrections apply)",
                               70, 65),
    "tbd": NoiseLimit("tbd", "To be determined by the consultant",
                      None, None),
}

# Table 8 — corrections at construction work sites
CONSTRUCTION_CORRECTIONS: List[Tuple[str, int]] = [
    ("Up to 2.5 hours", 10),
    ("From 2.5 to 8 hours", 5),
]


@dataclass
class NoiseVerdict:
    period: str                  # "day" | "night"
    measured: float
    limit: float
    margin: float                # measured - limit; negative is under
    status: str                  # "ok" | "over"
    text: str


def assess(summary: NoiseSummary, category: str) -> List[NoiseVerdict]:
    """Measured day and night levels against the campaign's category.

    An empty list means no judgement is made — the "to be determined"
    posture, in which the report states the levels against every category
    and leaves the assessment to the consultant.
    """
    limit = NOISE_LIMITS.get(category)
    if limit is None or limit.day_db is None:
        return []
    out: List[NoiseVerdict] = []
    for period, measured, lim in (("day", summary.l_day, limit.day_db),
                                  ("night", summary.l_night, limit.night_db)):
        if measured is None:
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
        out.append(NoiseVerdict(period=period, measured=measured, limit=lim,
                                margin=margin, status=status, text=text))
    return out
