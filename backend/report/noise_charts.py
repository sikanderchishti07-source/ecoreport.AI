# -*- coding: utf-8 -*-
"""The four noise-report charts, drawn from a NoiseSummary.

Same visual language as the air charts: navy title, muted subtitle, bold
figure chips top-right, dashed limit lines, light grid, provenance footer.
Sized for a 164 mm insert.
"""
from __future__ import annotations

import os
from datetime import timedelta
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates          # noqa: E402
import matplotlib.pyplot as plt            # noqa: E402

from noise_calc import NOISE_LIMITS, NoiseSummary  # noqa: E402

NAVY = "#123a6d"
BLUE = "#2e6fb7"
LBLUE = "#a8c8e8"
RED = "#b02a2a"
AMBER = "#c7791f"
GREY = "#8a8f98"
NIGHT = "#0d2340"

MM = 1 / 25.4
FIG_W, FIG_H = 164 * MM, 72 * MM
DPI = 220

_RC = {"font.family": "DejaVu Sans", "axes.edgecolor": "#d7dbe0",
       "axes.linewidth": 0.8, "axes.grid": True, "grid.color": "#e8ebef",
       "grid.linewidth": 0.7, "xtick.color": "#555", "ytick.color": "#555",
       "font.size": 8}


def _fig():
    plt.rcParams.update(_RC)
    fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=DPI)
    ax = fig.add_axes([0.075, 0.17, 0.905, 0.60])
    return fig, ax


def _chrome(fig, title, sub, chips):
    fig.text(0.055, 0.93, title, fontsize=12.5, fontweight="bold",
             color=NAVY)
    fig.text(0.055, 0.865, sub, fontsize=6.8, color=GREY)
    x = 0.985
    for lab, val in reversed(chips):
        fig.text(x, 0.905, val, fontsize=10, fontweight="bold", color=NAVY,
                 ha="right")
        fig.text(x, 0.955, lab, fontsize=5.6, color=GREY, ha="right")
        x -= 0.085
    fig.text(0.055, 0.02, "Generated from validated monitoring data",
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
                       alpha=0.05, lw=0)
    ax.plot(hk, hv, color=BLUE, lw=1.7, marker="o", ms=3.2, mfc="white",
            mec=BLUE, zorder=5)
    ax.fill_between(hk, hv, min(hv) - 4, color=BLUE, alpha=0.07, zorder=1)
    ymax = max(hv)
    lim = NOISE_LIMITS.get(category)
    if lim and lim.day_db is not None:
        ax.axhline(lim.day_db, color=RED, ls=(0, (6, 3)), lw=1.3)
        ax.axhline(lim.night_db, color=AMBER, ls=(0, (6, 3)), lw=1.3)
        ax.text(hk[-1], lim.day_db + 0.4,
                f"Day limit {lim.day_db:.0f} dB(A)", ha="right",
                fontsize=6.2, color=RED, fontweight="bold")
        ax.text(hk[-1], lim.night_db + 0.4,
                f"Night limit {lim.night_db:.0f} dB(A)", ha="right",
                fontsize=6.2, color=AMBER, fontweight="bold")
        ymax = max(ymax, lim.day_db)
        ax.set_ylim(min(min(hv), lim.night_db) - 4, ymax + 5)
    else:
        ax.set_ylim(min(hv) - 4, ymax + 5)
    im = max(range(len(hv)), key=lambda i: hv[i])
    ax.annotate(f"max {hv[im]:.1f}", (hk[im], hv[im]),
                textcoords="offset points", xytext=(6, 7), fontsize=6.5,
                fontweight="bold", color=NAVY)
    ax.set_ylabel("Hourly LAeq dB(A)", fontsize=7)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
    day = f"{s.day_start_hour:02d}:00–{s.day_end_hour:02d}:00"
    _chrome(fig, "Hourly LAeq",
            f"24-hour profile · energy-averaged per hour · shaded band is "
            f"the night period (day {day})",
            [("LAEQ", _f(s.laeq_t)), ("L DAY", _f(s.l_day)),
             ("L NIGHT", _f(s.l_night))])
    return _save(fig, out)


def chart_trace(s: NoiseSummary, readings: List[dict], out: str
                ) -> Optional[str]:
    valid = [r for r in readings if r.get("valid", True)
             and r.get("laeq") is not None]
    if not valid:
        return None
    fig, ax = _fig()
    ts = [r["timestamp"] for r in valid]
    v = [float(r["laeq"]) for r in valid]
    if s.la10 is not None and s.la90 is not None:
        ax.axhspan(s.la90, s.la10, color=LBLUE, alpha=0.35, lw=0)
        ax.text(ts[min(3, len(ts) - 1)], s.la10 + 0.3, f"LA10 {s.la10:.1f}",
                fontsize=6.2, color=NAVY, fontweight="bold")
        ax.text(ts[min(3, len(ts) - 1)], s.la90 - 1.3, f"LA90 {s.la90:.1f}",
                fontsize=6.2, color=NAVY, fontweight="bold")
    ax.plot(ts, v, color=BLUE, lw=0.55)
    imax = max(range(len(v)), key=lambda i: v[i])
    ax.plot(ts[imax], v[imax], "o", ms=4.5, color=RED)
    ax.annotate(f"Lmax {v[imax]:.1f}", (ts[imax], v[imax]),
                textcoords="offset points", xytext=(8, -2), fontsize=6.5,
                fontweight="bold", color=RED)
    ax.set_ylim(min(v) - 3, max(v) + 3)
    ax.set_ylabel("1-minute LAeq dB(A)", fontsize=7)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
    _chrome(fig, "Sound level record",
            f"One-minute resolution · {len(valid):,} intervals · shaded "
            f"band spans LA90 to LA10",
            [("LMAX", _f(s.lmax)), ("LA50", _f(s.la50)),
             ("LMIN", _f(s.lmin))])
    return _save(fig, out)


def chart_distribution(s: NoiseSummary, out: str) -> Optional[str]:
    if not s.dist_levels:
        return None
    fig, ax = _fig()
    ax.plot(s.dist_levels, s.dist_exceed, color=BLUE, lw=1.8)
    x0 = s.dist_levels[0]
    for pct, lab, val in ((10, "LA10", s.la10), (50, "LA50", s.la50),
                          (90, "LA90", s.la90)):
        if val is None:
            continue
        ax.plot([val, val], [0, pct], color=GREY, lw=0.8, ls=":")
        ax.plot([x0, val], [pct, pct], color=GREY, lw=0.8, ls=":")
        ax.plot(val, pct, "o", ms=4.2, color=NAVY)
        ax.annotate(f"{lab} = {val:.1f}", (val, pct),
                    textcoords="offset points", xytext=(7, 3), fontsize=6.5,
                    fontweight="bold", color=NAVY)
    ax.set_xlabel("Sound level dB(A)", fontsize=7)
    ax.set_ylabel("% of time exceeded", fontsize=7)
    ax.set_ylim(0, 100)
    _chrome(fig, "Statistical distribution",
            "Exceedance curve — percentile levels read directly from the "
            "measured record",
            [("LA10", _f(s.la10)), ("LA50", _f(s.la50)),
             ("LA90", _f(s.la90))])
    return _save(fig, out)


def chart_categories(s: NoiseSummary, out: str) -> Optional[str]:
    if s.l_day is None and s.l_night is None:
        return None
    fig, ax = _fig()
    cats = ["A", "B", "C", "D"]
    names = ["A\nSensitive", "B\nResidential", "C\nMixed", "D\nCommercial"]
    dlim = [NOISE_LIMITS[c].day_db for c in cats]
    nlim = [NOISE_LIMITS[c].night_db for c in cats]
    xx = list(range(4))
    w = 0.32
    ax.bar([x - w / 2 for x in xx], dlim, w, color=LBLUE, label="Day limit")
    ax.bar([x + w / 2 for x in xx], nlim, w, color="#cdd9ea",
           label="Night limit")
    top = max(dlim)
    if s.l_day is not None:
        ax.axhline(s.l_day, color=BLUE, lw=1.7)
        ax.text(3.44, s.l_day + 0.6, f"Measured L Day {s.l_day:.1f}",
                fontsize=6.4, color=BLUE, fontweight="bold", ha="right")
        top = max(top, s.l_day)
    if s.l_night is not None:
        ax.axhline(s.l_night, color=NIGHT, lw=1.7, ls=(0, (6, 3)))
        ax.text(3.44, s.l_night - 2.4, f"Measured L Night {s.l_night:.1f}",
                fontsize=6.4, color=NIGHT, fontweight="bold", ha="right")
        top = max(top, s.l_night)
    ax.set_xticks(xx)
    ax.set_xticklabels(names, fontsize=6.5)
    ax.set_ylabel("LAeq dB(A)", fontsize=7)
    ax.set_ylim(0, top + 10)
    ax.legend(fontsize=6, frameon=False, loc="upper left")
    _chrome(fig, "Measured levels vs NCEC categories",
            "Both measured levels drawn across the four land-use categories",
            [("L DAY", _f(s.l_day)), ("L NIGHT", _f(s.l_night))])
    return _save(fig, out)


def generate_noise_charts(s: NoiseSummary, readings: List[dict],
                          category: str, out_dir: str) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    figs: Dict[str, str] = {}
    for key, fn in (("hourly", lambda p: chart_hourly(s, category, p)),
                    ("trace", lambda p: chart_trace(s, readings, p)),
                    ("dist", lambda p: chart_distribution(s, p)),
                    ("cats", lambda p: chart_categories(s, p))):
        try:
            path = fn(os.path.join(out_dir, f"noise_{key}.png"))
            if path:
                figs[key] = path
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning(
                "noise chart %s failed", key, exc_info=True)
    return figs
