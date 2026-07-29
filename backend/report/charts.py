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
from matplotlib.patches import Patch

from calc import COMPASS_16, rolling_8h, _effective, _compass_bin, _speed_class
from models import Reading, WindClassBin
from report import chart_theme as T

SERIES_COLOR = "#1F6FB2"   # brand blue
LIMIT_COLOR = "#C00000"    # limit line — clear alarm red
SECOND_COLOR = "#2F9E63"   # accent green (secondary series)
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
    xn = mdates.date2num(xs)

    fig, ax = T.new_figure()
    valid = [v for v in ys if v is not None]
    if log:
        ax.set_yscale("log")
        top = max([limit or 0] + [v for v in valid if v > 0]) if (valid or limit) else 10
        ax.set_ylim(1, 10 ** math.ceil(math.log10(max(top, 10))))
    else:
        top = max([limit or 0] + valid) if (valid or limit) else 1
        ax.set_ylim(0, top * 1.18 if top else 1)

    if not log:
        T.gradient_under(ax, xn, [math.nan if v is None else v for v in ys])
    exceeded = T.exceedance_fill(ax, xn, ys, limit) if limit is not None else False
    T.series_line(ax, xs, ys, label=series_label)
    if limit is not None:
        T.limit_line(ax, limit, limit_label or "NCEC limit", xn, ys)
    T.peak_marker(ax, xs, ys)

    T.style_axes(ax, ylabel)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))

    T.header(fig, series_label, "Hourly averages at the monitoring station"
             + (" · compared with the NCEC 2020 standard" if limit is not None else ""))
    T.stat_chips(fig, T.fmt_stats(ys))
    handles = [plt.Line2D([], [], color=T.BLUE, lw=2.0, label=series_label)]
    if limit is not None:
        handles.append(plt.Line2D([], [], color=T.RED, lw=1.4, ls=(0, (7, 3)),
                                  label=limit_label or "NCEC limit"))
    if exceeded:
        handles.append(Patch(facecolor=T.RED, alpha=0.18, label="Exceedance"))
    T.legend_below(ax, handles)
    T.footnote(fig)
    return T.save(fig, out_path)


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
    fig, ax = T.new_figure()
    allv = [v for v in ya + yb if v is not None]
    ax.set_ylim(0, (max(allv) * 1.18) if allv else 1)
    T.series_line(ax, xs, ya, color=T.BLUE, label=label_a)
    T.series_line(ax, xs, yb, color=T.GREEN, label=label_b, width=1.8)
    T.style_axes(ax, ylabel)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
    T.header(fig, f"{label_a} vs {label_b}",
             "Hourly averages at the monitoring station")
    T.legend_below(ax, [plt.Line2D([], [], color=T.BLUE, lw=2.0, label=label_a),
                        plt.Line2D([], [], color=T.GREEN, lw=1.8, label=label_b)],
                   ncol=2)
    T.footnote(fig)
    return T.save(fig, out_path)


# ---------------------------------------------------------------------------
# Wind rose + wind class frequency distribution
# ---------------------------------------------------------------------------
ROSE_COLORS = ["#0F3D6E", "#1F6FB2", "#5BA3D9", "#9DC7E8", "#2F9E63", "#F2B705"]


def wind_rose_chart(
    readings: List[Reading],
    bins: List[WindClassBin],
    out_path: str,
    project_name: str = "",
    station_label: str = "AAQMS",
    window_text: str = "",
    window_start=None,
    window_end=None,
) -> str:
    """Wind rose drawn as a technical plate.

    Laid out the way a survey plot is: the rose itself, a stacked bar showing
    how the whole survey divides between speed classes, and a panel carrying
    the figures a reviewer checks — period, record count, mean and maximum
    speed, prevailing direction, calms.

    Calm hours have no direction, so they cannot be a petal. They are shown
    on a disc at the centre instead, which also accounts for the hollow
    middle rather than leaving it looking like a drawing artefact.

    Colours run across the campaign's own speed classes, so a campaign with
    two bands and one with six both come out legible.
    """
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle

    RAMP = LinearSegmentedColormap.from_list(
        "spd", ["#BFDCEF", "#5BA3D9", "#1F8FBF", "#17A398", "#3FAE62"])
    RULE = "#D6DFE8"
    RED = "#C0392B"

    pairs = []
    for r in readings:
        sp = _effective(r, "WindSpeed")
        di = _effective(r, "WindDirection")
        if sp is not None and di is not None:
            pairs.append((sp, di))
    total = len(pairs)

    non_calm = [b for b in bins
                if b.label.strip().lower() not in ("calm", "calms")]
    counts = {b.label: [0] * 16 for b in non_calm}
    calm = 0
    for sp, di in pairs:
        cls = _speed_class(sp, bins)
        if cls in counts:
            counts[cls][COMPASS_16.index(_compass_bin(di))] += 1
        else:
            calm += 1

    freqs, labels, class_tot = [], [], []
    for b in non_calm:
        c = np.asarray(counts[b.label], dtype=float)
        freqs.append(c / total * 100.0 if total else np.zeros(16))
        labels.append(b.label)
        class_tot.append(int(c.sum()))
    if not freqs:
        freqs, labels, class_tot = [np.zeros(16)], ["\u2014"], [0]
    colours = [RAMP(i / max(len(freqs) - 1, 1)) for i in range(len(freqs))]

    speeds = [sp for sp, _ in pairs]
    mean_sp = float(np.mean(speeds)) if speeds else 0.0
    max_sp = float(np.max(speeds)) if speeds else 0.0
    calm_pct = (calm / total * 100.0) if total else 0.0

    T.apply_theme()
    fig = plt.figure(figsize=(T.FIG_W, T.FIG_W * 0.667), dpi=T.DPI)
    fig.patch.set_facecolor("white")

    fig.patches.append(Rectangle((0.012, 0.015), 0.976, 0.970, fill=False,
                                 edgecolor=RULE, linewidth=1.2,
                                 transform=fig.transFigure, zorder=1))
    fig.patches.append(Rectangle((0.012, 0.897), 0.976, 0.088,
                                 facecolor=T.NAVY, edgecolor="none",
                                 transform=fig.transFigure, zorder=2))
    fig.text(0.030, 0.952, "WIND ROSE", color="white", fontsize=13,
             fontweight="bold", va="center")
    fig.text(0.030, 0.921,
             "Frequency of counts by wind direction (blowing from)",
             color="#C3D6E8", fontsize=8.0, va="center")
    if project_name:
        fig.text(0.970, 0.952, project_name.upper()[:34], color="white",
                 fontsize=9.5, fontweight="bold", ha="right", va="center")
    sub = " \u00b7 ".join(x for x in (station_label, window_text) if x)
    if sub:
        fig.text(0.970, 0.921, sub[:52], color="#C3D6E8", fontsize=8.0,
                 ha="right", va="center")

    # ---- rose --------------------------------------------------------
    ax = fig.add_axes([0.045, 0.215, 0.535, 0.655], projection="polar")
    ax.set_facecolor("white")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    th = np.deg2rad(np.arange(0, 360, 22.5))
    stacked = np.sum(freqs, axis=0)
    top = max(float(stacked.max()), 1.0)
    hole = top * 0.16
    ax.set_ylim(0, top * 1.10 + hole)

    bottom = np.full(16, hole)
    for i, f in enumerate(freqs):
        ax.bar(th, f, width=np.deg2rad(19.0), bottom=bottom, color=colours[i],
               edgecolor="white", linewidth=1.0, zorder=4)
        bottom += f

    rings = np.linspace(top / 5, top, 5)
    ax.set_yticks(rings + hole)
    ax.set_yticklabels([f"{r:.0f}%" for r in rings], fontsize=7.0,
                       color=T.MUTED)
    ax.set_rlabel_position(58)
    ax.set_xticks(th)
    ax.set_xticklabels([])
    ax.grid(color=RULE, linewidth=0.8, linestyle=(0, (2, 3)))
    ax.spines["polar"].set_color(RULE)

    ax.scatter([0], [0], s=1150, facecolor=T.NAVY, edgecolor="white",
               linewidth=1.6, zorder=6)
    ax.text(0, 0, f"{calm_pct:.0f}%\ncalm", ha="center", va="center",
            fontsize=7.4, color="white", fontweight="bold", zorder=7,
            linespacing=1.2)

    prevailing = COMPASS_16[int(np.argmax(stacked))] if stacked.max() else "\u2014"
    if stacked.max():
        pi = int(np.argmax(stacked))
        ax.annotate("", xy=(th[pi], top * 1.02 + hole),
                    xytext=(th[pi], top * 1.10 + hole),
                    arrowprops=dict(arrowstyle="-|>", color=RED, lw=2.2),
                    zorder=8)

    for lbl, ang in (("N", 0), ("NE", 45), ("E", 90), ("SE", 135),
                     ("S", 180), ("SW", 225), ("W", 270), ("NW", 315)):
        big = lbl in ("N", "E", "S", "W")
        ax.text(np.deg2rad(ang), top * 1.24 + hole, lbl, ha="center",
                va="center", fontsize=9.5 if big else 7.4,
                color=T.INK if big else T.MUTED,
                fontweight="bold" if big else "normal")

    # ---- distribution bar --------------------------------------------
    bx, bw, by, bh = 0.055, 0.520, 0.105, 0.042
    fig.text(bx, by + bh + 0.028, "SPEED CLASS DISTRIBUTION", fontsize=7.0,
             color=T.NAVY, fontweight="bold", va="center")
    fig.text(bx + bw, by + bh + 0.028, "m/s", fontsize=7.0, color=T.MUTED,
             ha="right", va="center")
    segs = [(calm / total if total else 0, "white", "Calm")]
    segs += [(class_tot[i] / total if total else 0, colours[i], labels[i])
             for i in range(len(freqs))]
    x = bx
    for frac, c, lab in segs:
        if frac <= 0:
            continue
        w = bw * frac
        fig.patches.append(Rectangle((x, by), w, bh, facecolor=c,
                                     edgecolor="white", linewidth=1.0,
                                     transform=fig.transFigure, zorder=4))
        if w > 0.035:
            fig.text(x + w / 2, by + bh / 2, f"{frac * 100:.0f}%",
                     fontsize=8.0,
                     color=T.INK if c == "white" else "white",
                     ha="center", va="center", fontweight="bold", zorder=5)
        x += w
    x = bx
    for frac, c, lab in segs:
        if frac <= 0:
            continue
        w = bw * frac
        if w > 0.055:
            fig.text(x + w / 2, by - 0.026, lab, fontsize=6.8, color=T.MUTED,
                     ha="center", va="center")
        x += w

    # ---- panel --------------------------------------------------------
    px, pw = 0.628, 0.332

    def _rule(y, w=0.9, c=RULE):
        fig.add_artist(Line2D([px, px + pw], [y, y], color=c, lw=w))

    def _head(y, t):
        fig.text(px, y, t, fontsize=7.0, color=T.NAVY, fontweight="bold",
                 va="center")
        _rule(y - 0.020, 1.0, T.NAVY)

    def _row(y, k, v):
        fig.text(px, y, k, fontsize=8.0, color=T.MUTED, va="center")
        fig.text(px + pw, y, v, fontsize=8.0, color=T.INK, ha="right",
                 va="center", fontweight="bold")

    fmt = "%d %b %Y  %H:%M"
    y = 0.828
    _head(y, "SURVEY")
    y -= 0.058
    for k, v in (("Start", window_start.strftime(fmt) if window_start else "\u2014"),
                 ("End", window_end.strftime(fmt) if window_end else "\u2014"),
                 ("Valid records", f"{total} hours")):
        _row(y, k, v)
        y -= 0.048
    y -= 0.010
    _rule(y)
    y -= 0.040

    _head(y, "WIND CHARACTER")
    y -= 0.058
    for k, v in (("Mean speed", f"{mean_sp:.2f} m/s"),
                 ("Maximum", f"{max_sp:.2f} m/s"),
                 ("Prevailing", prevailing),
                 ("Calms", f"{calm_pct:.2f}%")):
        _row(y, k, v)
        y -= 0.048
    y -= 0.010
    _rule(y)
    y -= 0.040

    _head(y, "SPEED CLASSES")
    y -= 0.058
    for i, lab in enumerate(labels):
        fig.patches.append(Rectangle((px, y - 0.013), 0.026, 0.026,
                                     facecolor=colours[i], edgecolor=T.INK,
                                     linewidth=0.5, transform=fig.transFigure,
                                     zorder=5))
        fig.text(px + 0.038, y, f"{lab} m/s", fontsize=8.0, color=T.INK,
                 va="center")
        fig.text(px + pw, y,
                 f"{(class_tot[i] / total * 100) if total else 0:.1f}%",
                 fontsize=8.0, color=T.MUTED, ha="right", va="center")
        y -= 0.048
    fig.patches.append(Rectangle((px, y - 0.013), 0.026, 0.026,
                                 facecolor="white", edgecolor=T.INK,
                                 linewidth=0.5, transform=fig.transFigure,
                                 zorder=5))
    fig.text(px + 0.038, y, "Calms", fontsize=8.0, color=T.INK, va="center")
    fig.text(px + pw, y, f"{calm_pct:.1f}%", fontsize=8.0, color=T.MUTED,
             ha="right", va="center")

    fig.text(px, 0.045, T.SOURCE_NOTE, fontsize=6.6, color=T.FAINT)
    fig.savefig(out_path, dpi=T.DPI, facecolor="white")
    plt.close(fig)
    return out_path


def wind_class_frequency_chart(
    class_frequency_pct: Dict[str, float],
    out_path: str,
) -> str:
    labels = list(class_frequency_pct.keys())
    vals = [class_frequency_pct[k] for k in labels]
    fig, ax = T.new_figure(height=3.6)
    bars = ax.bar(labels, vals, width=0.62, zorder=3,
                  color=[T.ROSE_SCALE[i % len(T.ROSE_SCALE)]
                         for i in range(len(labels))],
                  edgecolor="white", linewidth=1.0)
    top = max(vals + [1]) * 1.2
    ax.set_ylim(0, top)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + top * 0.03, f"{v:.1f}%",
                ha="center", fontsize=8.2, fontweight="bold", color=T.NAVY)
    T.style_axes(ax, "Frequency of occurrence (%)", "Wind class (m/s)")
    T.header(fig, "Wind Class Frequency Distribution",
             "Share of valid hourly records in each wind speed class")
    T.footnote(fig)
    return T.save(fig, out_path)


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
    window_end=None,
    project_name: str = "",
    window_text: str = "",
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
    figs["wind_rose"] = wind_rose_chart(
        readings, bins, p("fig_windrose.png"),
        project_name=project_name, window_start=window_start,
        window_end=window_end, window_text=window_text)
    if class_frequency_pct is not None:
        figs["wind_class_freq"] = wind_class_frequency_chart(
            class_frequency_pct, p("fig_windclassfreq.png"))
    return figs
