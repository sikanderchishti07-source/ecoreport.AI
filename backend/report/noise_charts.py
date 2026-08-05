# -*- coding: utf-8 -*-
"""The noise-report charts, drawn from a NoiseSummary.

Same visual language as the air charts: navy title, muted subtitle, bold
figure chips top-right, dashed limit lines, light grid, provenance footer.
Sized for a 164 mm insert.

Two faults from the first version are fixed here and are worth naming so
they are not reintroduced. The time axis used a fixed four-hour tick, which
drew an unreadable smear of labels on any window longer than a day or two;
it now scales with the window. And the record's subtitle was hardcoded to
"One-minute resolution", contradicting its own caption the moment a
per-second logger was used; it now takes the interval measured from the
data.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates          # noqa: E402
import matplotlib.pyplot as plt            # noqa: E402

from noise_calc import NOISE_LIMITS, NoiseSummary  # noqa: E402

log = logging.getLogger(__name__)

NAVY = "#123a6d"
BLUE = "#2e6fb7"
LBLUE = "#a8c8e8"
RED = "#b02a2a"
AMBER = "#c7791f"
GREEN = "#1e7d4f"
GREY = "#8a8f98"
NIGHT = "#0d2340"

MM = 1 / 25.4
FIG_W, FIG_H = 164 * MM, 74 * MM
DPI = 220

_RC = {"font.family": "DejaVu Sans", "axes.edgecolor": "#d7dbe0",
       "axes.linewidth": 0.8, "axes.grid": True, "grid.color": "#eceff3",
       "grid.linewidth": 0.7, "xtick.color": "#555", "ytick.color": "#555",
       "font.size": 8}


def _fig(left: float = 0.078):
    plt.rcParams.update(_RC)
    fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=DPI)
    ax = fig.add_axes([left, 0.19, 0.978 - left, 0.575])
    return fig, ax


def _time_axis(ax, t0: datetime, t1: datetime) -> None:
    """Tick spacing suited to the window. A fixed locator cannot serve both
    a six-hour spot check and a two-month campaign; at four-hourly ticks the
    latter drew several hundred labels on top of each other."""
    hours = max(0.1, (t1 - t0).total_seconds() / 3600.0)
    if hours <= 6:
        loc, fmt = mdates.MinuteLocator(byminute=[0, 30]), "%H:%M"
    elif hours <= 30:
        loc, fmt = mdates.HourLocator(interval=3), "%d %b\n%H:%M"
    elif hours <= 96:
        loc, fmt = mdates.HourLocator(interval=12), "%d %b\n%H:%M"
    elif hours <= 24 * 14:
        loc, fmt = mdates.DayLocator(interval=1), "%d %b"
    elif hours <= 24 * 70:
        loc, fmt = mdates.DayLocator(interval=7), "%d %b"
    else:
        loc, fmt = mdates.MonthLocator(), "%b %Y"
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
    for lbl in ax.get_xticklabels():
        lbl.set_fontsize(6.4)


def _interval_phrase(seconds: float) -> str:
    if seconds <= 1.5:
        return "One-second"
    if seconds < 55:
        return f"{int(round(seconds))}-second"
    if seconds <= 65:
        return "One-minute"
    mins = seconds / 60.0
    return (f"{int(round(mins))}-minute" if abs(mins - round(mins)) < 0.05
            else f"{mins:.1f}-minute")


def _chrome(fig, title, sub, chips):
    fig.text(0.055, 0.935, title, fontsize=12.5, fontweight="bold",
             color=NAVY)
    fig.text(0.055, 0.872, sub, fontsize=6.8, color=GREY)
    x = 0.985
    for lab, val in reversed(chips):
        fig.text(x, 0.908, val, fontsize=10, fontweight="bold", color=NAVY,
                 ha="right")
        fig.text(x, 0.957, lab, fontsize=5.6, color=GREY, ha="right")
        x -= 0.088
    fig.text(0.055, 0.025, "Generated from validated monitoring data",
             fontsize=5.6, color="#b7bcc4")


def _f(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.1f}"


def _save(fig, path):
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


def chart_hourly(s: NoiseSummary, category: str, out: str) -> Optional[str]:
    if not s.hourly:
        return None
    fig, ax = _fig()
    hk = [h.hour for h in s.hourly]
    hv = [h.laeq for h in s.hourly]
    for h in s.hourly:
        if not h.is_day:
            ax.axvspan(h.hour, h.hour + timedelta(hours=1), color=NIGHT,
                       alpha=0.055, lw=0)
    lim = NOISE_LIMITS.get(category)
    has_lim = bool(lim and lim.day_db is not None)
    lo, hi = min(hv) - 5, max(hv) + 7
    if has_lim:
        lo = min(lo, lim.night_db - 5)
        hi = max(hi, lim.day_db + 7)
    ax.fill_between(hk, hv, lo, color=BLUE, alpha=0.09, zorder=1)
    ax.plot(hk, hv, color=BLUE, lw=1.8, marker="o", ms=3.4, mfc="white",
            mec=BLUE, zorder=5)
    if has_lim:
        # Hours over the limit are ringed: an exceedance should be findable
        # on the chart, not only in the verdict text.
        over = [(k, v) for k, v in zip(hk, hv) if v > lim.day_db]
        if over:
            ax.plot([o[0] for o in over], [o[1] for o in over], "o", ms=5,
                    color=RED, zorder=6)
        ax.axhline(lim.day_db, color=RED, ls=(0, (6, 3)), lw=1.3, zorder=4)
        ax.axhline(lim.night_db, color=AMBER, ls=(0, (6, 3)), lw=1.3,
                   zorder=4)
        ax.text(hk[0], lim.day_db + 0.7, f"Day limit {lim.day_db:.0f} dB(A)",
                fontsize=6.2, color=RED, fontweight="bold")
        ax.text(hk[0], lim.night_db + 0.7,
                f"Night limit {lim.night_db:.0f} dB(A)", fontsize=6.2,
                color=AMBER, fontweight="bold")
    im = max(range(len(hv)), key=lambda i: hv[i])
    ax.annotate(f"{hv[im]:.1f}", (hk[im], hv[im]),
                textcoords="offset points", xytext=(0, 9), ha="center",
                fontsize=6.6, fontweight="bold", color=NAVY)
    ax.set_ylim(lo, hi)
    ax.set_ylabel("Hourly LAeq dB(A)", fontsize=7)
    _time_axis(ax, hk[0], hk[-1] + timedelta(hours=1))
    day = f"{s.day_start_hour:02d}:00–{s.day_end_hour:02d}:00"
    sub = (f"Energy-averaged per hour · shaded band is the night period "
           f"(day {day})")
    if has_lim:
        sub += " · hours above the day limit ringed in red"
    _chrome(fig, "Hourly LAeq", sub,
            [("LAEQ", _f(s.laeq_t)), ("L DAY", _f(s.l_day)),
             ("L NIGHT", _f(s.l_night))])
    return _save(fig, out)


def chart_day_night(s: NoiseSummary, out: str,
                    category: str = "tbd") -> Optional[str]:
    """Day and night against the applicable limit.

    The figure a client reads first: it answers "did we comply" without
    needing to interpret anything. Omitted when no category is chosen —
    there is no limit to compare against, and inventing one would be the
    opposite of what that choice means.
    """
    lim = NOISE_LIMITS.get(category)
    if not lim or lim.day_db is None:
        return None
    if s.l_day is None and s.l_night is None:
        return None
    fig, ax = _fig(left=0.145)
    labels = [f"Day {s.day_start_hour:02d}:00–{s.day_end_hour:02d}:00",
              f"Night {s.day_end_hour:02d}:00–{s.day_start_hour:02d}:00"]
    meas = [s.l_day, s.l_night]
    lims = [lim.day_db, lim.night_db]
    y = list(range(2))
    ax.barh(y, lims, 0.42, color="#e3eaf3", edgecolor="#c3cedb", lw=0.6,
            label="NCEC limit", zorder=3)
    cols = [RED if (m is not None and m > l) else GREEN
            for m, l in zip(meas, lims)]
    ax.barh(y, [m or 0 for m in meas], 0.22, color=cols, zorder=4,
            label="Measured")
    for i, (m, l) in enumerate(zip(meas, lims)):
        if m is None:
            continue
        d = m - l
        txt = (f"{m:.1f} dB(A)   " +
               (f"{d:+.1f} dB vs limit" if d > 0
                else f"{abs(d):.1f} dB below limit"))
        ax.text(max(m, l) + 1.5, i, txt, va="center", fontsize=6.8,
                fontweight="bold", color=RED if d > 0 else GREEN)
        ax.text(l, i - 0.30, f"limit {l:.0f}", fontsize=6, color="#6b7280",
                ha="center")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlim(0, max([x for x in meas if x is not None] + lims) + 34)
    ax.set_xlabel("LAeq dB(A)", fontsize=7)
    ax.grid(axis="y", visible=False)
    ax.legend(fontsize=6, frameon=False, loc="upper right", ncol=2,
              bbox_to_anchor=(1.0, 1.14))
    _chrome(fig, "Day and night against the applicable limit",
            f"{lim.label} — {lim.day_db:.0f} dB(A) day, "
            f"{lim.night_db:.0f} dB(A) night",
            [("L DAY", _f(s.l_day)), ("L NIGHT", _f(s.l_night))])
    return _save(fig, out)


def chart_categories(s: NoiseSummary, out: str,
                     category: str = "tbd") -> Optional[str]:
    if s.l_day is None and s.l_night is None:
        return None
    fig, ax = _fig()
    cats = ["A", "B", "C", "D"]
    names = ["A\nSensitive", "B\nResidential", "C\nMixed", "D\nCommercial"]
    dl = [NOISE_LIMITS[c].day_db for c in cats]
    nl = [NOISE_LIMITS[c].night_db for c in cats]
    xx = list(range(4))
    w = 0.34
    b1 = ax.bar([x - w / 2 for x in xx], dl, w, color="#bcd4ec",
                edgecolor="#8fb4d8", lw=0.6, label="Day limit", zorder=3)
    b2 = ax.bar([x + w / 2 for x in xx], nl, w, color="#e0e7f0",
                edgecolor="#b9c6d6", lw=0.6, label="Night limit", zorder=3)
    for bars in (b1, b2):
        for r in bars:
            ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.8,
                    f"{r.get_height():.0f}", ha="center", fontsize=6,
                    color="#6b7280", zorder=4)
    top = max(dl)
    for val, col, lab in ((s.l_day, BLUE, "Measured L Day"),
                          (s.l_night, NIGHT, "Measured L Night")):
        if val is None:
            continue
        top = max(top, val)
        ax.axhline(val, color=col, lw=2 if col == BLUE else 1.6,
                   ls="-" if col == BLUE else (0, (5, 3)), zorder=5)
        # Labels sit inside the plot on a white pad; placed outside they ran
        # off the figure, and placed bare they collided with the bars.
        ax.text(3.47, val + 1.1, f"{lab}  {val:.1f}", fontsize=6.6,
                color=col, fontweight="bold", ha="right", zorder=7,
                bbox=dict(fc="white", ec="none", alpha=0.85, pad=1.2))
    ax.set_xticks(xx)
    ax.set_xticklabels(names, fontsize=6.6)
    ax.set_ylabel("LAeq dB(A)", fontsize=7)
    ax.set_ylim(0, top + 13)
    ax.set_xlim(-0.62, 3.62)
    ax.legend(fontsize=6, frameon=False, loc="upper left", ncol=2)
    sub = "Both measured levels drawn across the four land-use categories"
    lim = NOISE_LIMITS.get(category)
    if lim and lim.day_db is not None and category not in cats:
        sub += (f" · applicable category is {lim.label.lower()} "
                f"({lim.day_db:.0f} / {lim.night_db:.0f} dB(A))")
    elif category in cats:
        sub += f" · applicable category is {category}"
    _chrome(fig, "Measured levels vs NCEC categories", sub,
            [("L DAY", _f(s.l_day)), ("L NIGHT", _f(s.l_night))])
    return _save(fig, out)


def chart_trace(s: NoiseSummary, readings: List[dict], out: str,
                category: str = "tbd") -> Optional[str]:
    valid = [r for r in readings
             if r.get("valid", True) and r.get("laeq") is not None]
    if not valid:
        return None
    fig, ax = _fig()
    ts = [r["timestamp"] for r in valid]
    v = [float(r["laeq"]) for r in valid]
    if s.la10 is not None and s.la90 is not None:
        ax.axhspan(s.la90, s.la10, color=LBLUE, alpha=0.4, lw=0, zorder=1)
        ax.text(ts[min(2, len(ts) - 1)], s.la10 + 0.8, f"LA10 {s.la10:.1f}",
                fontsize=6.2, color=NAVY, fontweight="bold", zorder=6)
        ax.text(ts[min(2, len(ts) - 1)], s.la90 - 2.4, f"LA90 {s.la90:.1f}",
                fontsize=6.2, color=NAVY, fontweight="bold", zorder=6)
    ax.plot(ts, v, color=BLUE, lw=0.35, alpha=0.85, zorder=3)
    i = max(range(len(v)), key=lambda k: v[k])
    ax.plot(ts[i], v[i], "o", ms=5, color=RED, zorder=6)
    ax.annotate(f"Lmax {v[i]:.1f} dB(A)\n{ts[i]:%H:%M}", (ts[i], v[i]),
                textcoords="offset points", xytext=(-14, -6), ha="right",
                fontsize=6.4, fontweight="bold", color=RED)
    lim = NOISE_LIMITS.get(category)
    if lim and lim.day_db is not None:
        ax.axhline(lim.day_db, color=RED, ls=(0, (6, 3)), lw=1.0, alpha=0.8,
                   zorder=4)
        ax.text(ts[-1], lim.day_db + 1.2, f"Day limit {lim.day_db:.0f}",
                fontsize=6, color=RED, ha="right", fontweight="bold")
    ax.set_ylim(min(v) - 3, max(v) + 6)
    ax.set_ylabel("LAeq dB(A)", fontsize=7)
    _time_axis(ax, ts[0], ts[-1])
    _chrome(fig, "Sound level record",
            f"{_interval_phrase(getattr(s, 'interval_seconds', 60.0))} "
            f"resolution · {len(valid):,} intervals · shaded band spans "
            f"LA90 to LA10",
            [("LMAX", _f(s.lmax)), ("LA50", _f(s.la50)),
             ("LMIN", _f(s.lmin))])
    return _save(fig, out)


def chart_distribution(s: NoiseSummary, readings: List[dict], out: str,
                       category: str = "tbd") -> Optional[str]:
    if not s.dist_levels:
        return None
    fig, ax = _fig()
    ax.fill_between(s.dist_levels, s.dist_exceed, 0, color=BLUE, alpha=0.09)
    ax.plot(s.dist_levels, s.dist_exceed, color=BLUE, lw=2, zorder=4)
    x0 = s.dist_levels[0]
    for pct, lab, val in ((10, "LA10", s.la10), (50, "LA50", s.la50),
                          (90, "LA90", s.la90)):
        if val is None:
            continue
        ax.plot([val, val], [0, pct], color=GREY, lw=0.8, ls=":", zorder=3)
        ax.plot([x0, val], [pct, pct], color=GREY, lw=0.8, ls=":", zorder=3)
        ax.plot(val, pct, "o", ms=4.6, color=NAVY, zorder=6)
        ax.annotate(f"{lab} = {val:.1f}", (val, pct),
                    textcoords="offset points", xytext=(8, 4), fontsize=6.5,
                    fontweight="bold", color=NAVY)
    lim = NOISE_LIMITS.get(category)
    if lim and lim.day_db is not None:
        vals = [float(r["laeq"]) for r in readings
                if r.get("valid", True) and r.get("laeq") is not None]
        if vals:
            above = 100.0 * sum(1 for x in vals if x > lim.day_db) / len(vals)
            ax.axvline(lim.day_db, color=RED, ls=(0, (6, 3)), lw=1.1,
                       zorder=4)
            ax.text(lim.day_db - 0.8, 86,
                    f"Day limit {lim.day_db:.0f} dB(A)\n"
                    f"exceeded {above:.1f}% of the time",
                    fontsize=6.2, color=RED, fontweight="bold", ha="right",
                    bbox=dict(fc="white", ec="none", alpha=0.85, pad=1.5))
    ax.set_xlabel("Sound level dB(A)", fontsize=7)
    ax.set_ylabel("% of time exceeded", fontsize=7)
    ax.set_ylim(0, 100)
    _chrome(fig, "Statistical distribution",
            "Exceedance curve — percentile levels read directly from the "
            "measured record",
            [("LA10", _f(s.la10)), ("LA50", _f(s.la50)),
             ("LA90", _f(s.la90))])
    return _save(fig, out)


def generate_noise_charts(s: NoiseSummary, readings: List[dict],
                          category: str, out_dir: str) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    figs: Dict[str, str] = {}
    for key, fn in (
        ("hourly", lambda p: chart_hourly(s, category, p)),
        ("daynight", lambda p: chart_day_night(s, p, category)),
        ("cats", lambda p: chart_categories(s, p, category)),
        ("trace", lambda p: chart_trace(s, readings, p, category)),
        ("dist", lambda p: chart_distribution(s, readings, p, category)),
    ):
        try:
            path = fn(os.path.join(out_dir, f"noise_{key}.png"))
            if path:
                figs[key] = path
        except Exception:  # noqa: BLE001
            log.warning("noise chart %s failed", key, exc_info=True)
    return figs
