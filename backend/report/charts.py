"""Phase 3/4 — dynamic chart generation matching the BSA gold-standard report.

Every chart is regenerated from the campaign's readings on each report build.
Style replicates the sample report's Excel-look figures: blue data series,
orange/red NCEC limit line, legend at bottom, x-axis label "m/d/y h:m",
log scale for CO charts.
"""
from __future__ import annotations

import math
import os
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from calc import COMPASS_16, rolling_8h, _effective, _compass_bin, _speed_class
from models import Reading, WindClassBin

SERIES_COLOR = "#4472C4"   # Excel default blue
LIMIT_COLOR = "#ED7D31"    # Excel default orange
SECOND_COLOR = "#A5A5A5"
FIG_SIZE = (7.5, 3.4)
DPI = 150

X_LABEL = "m/d/y h:m"


def _xy(readings: List[Reading], field: str) -> Tuple[List[datetime], List[Optional[float]]]:
    xs = [r.timestamp for r in readings]
    ys = [_effective(r, field) for r in readings]
    return xs, ys


def _fmt_axes(ax, ylabel: str):
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_xlabel(X_LABEL, fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m-%-d-%y %H:%M"))
    ax.tick_params(labelsize=8)
    for lbl in ax.get_xticklabels():
        lbl.set_rotation(0)
    ax.grid(True, linewidth=0.4, alpha=0.5)
    ax.spines[["top", "right"]].set_visible(False)


def _save(fig, out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return out_path


def timeseries_chart(
    readings: List[Reading],
    field: str,
    out_path: str,
    ylabel: str,
    series_label: str,
    limit: Optional[float] = None,
    limit_label: Optional[str] = None,
    log: bool = False,
    values: Optional[Sequence[Optional[float]]] = None,
) -> str:
    """Generic hourly time-series with optional NCEC limit line.
    `values` overrides the raw field (used for 8-hr rolling series)."""
    xs = [r.timestamp for r in readings]
    ys = list(values) if values is not None else [_effective(r, field) for r in readings]
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    ax.plot(xs, [y if y is not None else math.nan for y in ys],
            color=SERIES_COLOR, linewidth=1.4, label=series_label)
    handles_extra = []
    if limit is not None:
        ax.axhline(limit, color=LIMIT_COLOR, linewidth=1.6,
                   label=limit_label or f"NCEC limit")
    if log:
        ax.set_yscale("log")
        valid = [y for y in ys if y is not None and y > 0]
        top = max([limit or 0] + valid) if (valid or limit) else 10
        ax.set_ylim(1, 10 ** math.ceil(math.log10(max(top, 10)) ))
    else:
        valid = [y for y in ys if y is not None]
        top = max([limit or 0] + valid) if (valid or limit) else 1
        ax.set_ylim(0, top * 1.12 if top else 1)
    _fmt_axes(ax, ylabel)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22),
              ncol=2, fontsize=8, frameon=False)
    return _save(fig, out_path)


def dual_series_chart(
    readings: List[Reading],
    field_a: str, label_a: str,
    field_b: str, label_b: str,
    out_path: str,
    ylabel: str,
) -> str:
    """Two hourly series on one axis (NO2 vs O3 correlation figure)."""
    xs = [r.timestamp for r in readings]
    ya = [_effective(r, field_a) for r in readings]
    yb = [_effective(r, field_b) for r in readings]
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    ax.plot(xs, [v if v is not None else math.nan for v in ya],
            color=SERIES_COLOR, linewidth=1.4, label=label_a)
    ax.plot(xs, [v if v is not None else math.nan for v in yb],
            color=LIMIT_COLOR, linewidth=1.4, label=label_b)
    _fmt_axes(ax, ylabel)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22),
              ncol=2, fontsize=8, frameon=False)
    return _save(fig, out_path)


# ---------------------------------------------------------------------------
# Wind rose + wind class frequency distribution
# ---------------------------------------------------------------------------
ROSE_COLORS = ["#2E75B6", "#70AD47", "#FFC000", "#C00000", "#7030A0", "#ED7D31"]


def wind_rose_chart(
    readings: List[Reading],
    bins: List[WindClassBin],
    out_path: str,
) -> str:
    """Polar stacked wind rose over the campaign's configurable speed classes.
    Calm class is excluded from the petals (shown in caption tables instead),
    consistent with WRPLOT convention used in the gold-standard report."""
    pairs = []
    for r in readings:
        ws = _effective(r, "WindSpeed")
        wd = _effective(r, "WindDirection")
        if ws is not None and wd is not None:
            pairs.append((ws, wd))
    total = len(pairs)

    non_calm_bins = [b for b in bins if b.label.strip().lower() not in ("calm", "calms")]
    counts = {b.label: [0] * 16 for b in non_calm_bins}
    for ws, wd in pairs:
        cls = _speed_class(ws, bins)
        if cls is None or cls not in counts:
            continue
        idx = COMPASS_16.index(_compass_bin(wd))
        counts[cls][idx] += 1

    theta = np.deg2rad(np.arange(0, 360, 22.5))
    width = np.deg2rad(20)
    fig = plt.figure(figsize=(6.2, 6.2))
    ax = fig.add_subplot(111, projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    bottom = np.zeros(16)
    for i, b in enumerate(non_calm_bins):
        freq = np.array(counts[b.label]) / total * 100.0 if total else np.zeros(16)
        ax.bar(theta, freq, width=width, bottom=bottom,
               color=ROSE_COLORS[i % len(ROSE_COLORS)],
               edgecolor="white", linewidth=0.6,
               label=f"{b.label} m/s")
        bottom += freq
    ax.set_xticks(theta)
    ax.set_xticklabels(COMPASS_16, fontsize=9)
    ax.tick_params(axis="y", labelsize=8)
    ax.set_rlabel_position(112.5)
    ax.grid(linewidth=0.4, alpha=0.6)
    ax.set_title("Wind Rose — frequency (%) by direction and wind class",
                 fontsize=10, pad=18)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.06),
              ncol=min(len(non_calm_bins), 3), fontsize=8, frameon=False)
    return _save(fig, out_path)


def wind_class_frequency_chart(
    class_frequency_pct: Dict[str, float],
    out_path: str,
) -> str:
    labels = list(class_frequency_pct.keys())
    vals = [class_frequency_pct[k] for k in labels]
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    bars = ax.bar(labels, vals, color=[ROSE_COLORS[i % len(ROSE_COLORS)]
                                       for i in range(len(labels))])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.6, f"{v:.1f}%",
                ha="center", fontsize=8)
    ax.set_ylabel("Frequency (%)", fontsize=9)
    ax.set_xlabel("Wind Class (m/s)", fontsize=9)
    ax.set_ylim(0, max(vals + [1]) * 1.18)
    ax.tick_params(labelsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linewidth=0.4, alpha=0.5)
    return _save(fig, out_path)


# ---------------------------------------------------------------------------
# Full chart set for one campaign
# ---------------------------------------------------------------------------
def generate_all_charts(
    readings: List[Reading],
    bins: List[WindClassBin],
    limits: Dict[Tuple[str, str], float],
    out_dir: str,
    window_start=None,
    class_frequency_pct: Optional[Dict[str, float]] = None,
) -> Dict[str, str]:
    """Generate every figure of the gold-standard report. Returns
    {figure_key: file_path}. `limits` maps (pollutant, period) -> µg/m³."""
    os.makedirs(out_dir, exist_ok=True)
    p = lambda name: os.path.join(out_dir, name)
    figs: Dict[str, str] = {}

    def L(pol, per):
        return limits.get((pol, per))

    figs["so2_hourly"] = timeseries_chart(
        readings, "SO2", p("fig_so2.png"),
        "Hourly Concentration of SO2 (ug/m3)", "SO2",
        limit=L("SO2", "1 Hour"), limit_label="SO2 NCEC hr")
    figs["no_hourly"] = timeseries_chart(
        readings, "NO", p("fig_no.png"),
        "Hourly Concentration of NO (ug/m3)", "NO")
    figs["no2_hourly"] = timeseries_chart(
        readings, "NO2", p("fig_no2.png"),
        "Hourly Concentration of NO2 (ug/m3)", "NO2",
        limit=L("NO2", "1 Hour"), limit_label="NCEC limit for NO2")
    figs["nox_hourly"] = timeseries_chart(
        readings, "NOx", p("fig_nox.png"),
        "Hourly Concentration of NOX (ug/m3)", "NOX")
    figs["co_hourly"] = timeseries_chart(
        readings, "CO", p("fig_co.png"),
        "Hourly Concentration of CO (ug/m3)", "CO",
        limit=L("CO", "1 Hour"), limit_label="NCEC limit for CO", log=True)
    co_roll = rolling_8h(readings, "CO", window_start=window_start)
    figs["co_8h"] = timeseries_chart(
        readings, "CO", p("fig_co8h.png"),
        "Hourly concentration (ug/m3)", "CO (8 Hour rolling average)",
        limit=L("CO", "8 Hour (rolling)"), limit_label="CO (8 Hour NCEC)",
        log=True, values=co_roll)
    figs["h2s_hourly"] = timeseries_chart(
        readings, "H2S", p("fig_h2s.png"),
        "Hourly Concentration of H2S (ug/m3)", "H2S",
        limit=L("H2S", "1 Hour"), limit_label="H2S NCEC Hr")
    figs["o3_hourly"] = timeseries_chart(
        readings, "O3", p("fig_o3.png"),
        "Hourly Concentration of O3 (ug/m3)", "Ozone")
    o3_roll = rolling_8h(readings, "O3", window_start=window_start)
    figs["o3_8h"] = timeseries_chart(
        readings, "O3", p("fig_o38h.png"),
        "Hourly concentration (ug/m3)", "O3 (8 Hour rolling average)",
        limit=L("O3", "8 Hour (rolling)"), limit_label="O3 (8 Hour NCEC)",
        values=o3_roll)
    figs["no2_vs_o3"] = dual_series_chart(
        readings, "NO2", "NO2", "O3", "O3", p("fig_no2_o3.png"),
        "Hourly concentration (ug/m3)")
    figs["pm10_hourly"] = timeseries_chart(
        readings, "PM10", p("fig_pm10.png"),
        "Hourly concentration of PM10 (ug/m3)", "PM10",
        limit=L("PM10", "24 Hour"), limit_label="NCEC Limit for PM10")
    figs["pm25_hourly"] = timeseries_chart(
        readings, "PM25", p("fig_pm25.png"),
        "Hourly concentration of PM2.5 (ug/m3)", "PM 2.5",
        limit=L("PM25", "24 Hour"), limit_label="NCEC Limit for PM2.5")
    figs["temp"] = timeseries_chart(
        readings, "Temp", p("fig_temp.png"),
        "Hourly temperature (0C)", "Temperature")
    figs["rh"] = timeseries_chart(
        readings, "RH", p("fig_rh.png"),
        "Hourly Relative Humidity (%)", "Humidity")
    figs["pressure"] = timeseries_chart(
        readings, "Pressure", p("fig_pressure.png"),
        "Hourly Pressure (hPa)", "Pressure")
    figs["ws"] = timeseries_chart(
        readings, "WindSpeed", p("fig_ws.png"),
        "Hourly Wind Speed (m/s)", "Wind Speed")
    figs["wind_rose"] = wind_rose_chart(readings, bins, p("fig_windrose.png"))
    if class_frequency_pct is not None:
        figs["wind_class_freq"] = wind_class_frequency_chart(
            class_frequency_pct, p("fig_windclassfreq.png"))
    return figs
