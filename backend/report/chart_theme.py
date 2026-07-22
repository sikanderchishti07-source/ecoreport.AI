"""Chart design system for EcoReport AI.

One place defines typography, palette, spacing and the standard chart
"furniture" (header block, stat chips, footnote, gradient fill, smart limit
labelling). Every figure in the report is drawn through these helpers so the
whole document reads as one designed set rather than twenty separate plots.

Nothing here touches the numbers — it only controls how they are drawn.
"""
from __future__ import annotations

import math
import os
from typing import List, Optional, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyBboxPatch, Polygon

# ---------------------------------------------------------------------------
# Typography — professional sans with graceful fallback
# ---------------------------------------------------------------------------
FONT_STACK = ["IBM Plex Sans", "Inter", "Source Sans 3", "Noto Sans",
              "DejaVu Sans"]


def _resolve_font() -> str:
    available = {f.name for f in fm.fontManager.ttflist}
    for name in FONT_STACK:
        if name in available:
            return name
    return "DejaVu Sans"


FONT = _resolve_font()

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
NAVY = "#0F3D6E"        # headings, emphasis
BLUE = "#1F6FB2"        # primary data series
BLUE_LIGHT = "#5BA3D9"
GREEN = "#2F9E63"       # secondary series
RED = "#C0392B"         # regulatory limit / exceedance
INK = "#2C3A47"         # primary text
MUTED = "#6B7885"       # axis labels, secondary text
FAINT = "#A7B0BA"       # footnotes
GRID = "#EDF1F5"
AXIS = "#DCE3EA"
PANEL = "#F4F7FA"

ROSE_SCALE = ["#DCEBF7", "#A9CDE9", "#67A6D8", "#2A7CBE", "#0F3D6E", "#2F9E63"]

# ---------------------------------------------------------------------------
# Spacing scale (figure fractions) — consistent rhythm across all charts
# ---------------------------------------------------------------------------
DPI = 220
FIG_W, FIG_H = 7.6, 3.9
AX_LEFT, AX_RIGHT = 0.095, 0.975
AX_BOTTOM, AX_TOP = 0.215, 0.735      # room for header above, legend below
TITLE_Y, SUB_Y = 0.945, 0.868
CHIP_Y, CHIP_H = 0.845, 0.072
FOOT_Y = 0.035

SOURCE_NOTE = "Generated from validated monitoring data"


def apply_theme() -> None:
    """Global rcParams — call once per figure build."""
    plt.rcParams.update({
        "font.family": FONT,
        "font.size": 9,
        "text.color": INK,
        "axes.edgecolor": AXIS,
        "axes.labelcolor": MUTED,
        "axes.linewidth": 0.9,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "legend.frameon": False,
        "figure.dpi": DPI,
    })


# ---------------------------------------------------------------------------
# Chart furniture
# ---------------------------------------------------------------------------
def new_figure(height: float = FIG_H):
    apply_theme()
    fig = plt.figure(figsize=(FIG_W, height))
    ax = fig.add_axes([AX_LEFT, AX_BOTTOM, AX_RIGHT - AX_LEFT,
                       AX_TOP - AX_BOTTOM])
    return fig, ax


def header(fig, title: str, subtitle: str = "") -> None:
    fig.text(AX_LEFT, TITLE_Y, title, fontsize=12.5, fontweight="bold",
             color=NAVY, va="top")
    if subtitle:
        fig.text(AX_LEFT, SUB_Y, subtitle, fontsize=8.4, color=MUTED, va="top")


def stat_chips(fig, stats: Sequence[tuple]) -> None:
    """Right-aligned metric chips, e.g. [("MAX","14.7"),("MEAN","3.1")]."""
    if not stats:
        return
    w, gap = 0.096, 0.008
    total = len(stats) * w + (len(stats) - 1) * gap
    x = AX_RIGHT - total
    for label, value in stats:
        fig.patches.append(FancyBboxPatch(
            (x, CHIP_Y), w, CHIP_H, boxstyle="round,pad=0.004,rounding_size=0.012",
            transform=fig.transFigure, facecolor=PANEL, edgecolor=AXIS,
            linewidth=0.7, zorder=0))
        fig.text(x + w / 2, CHIP_Y + CHIP_H * 0.68, label, fontsize=6.2,
                 color=MUTED, ha="center", va="center", fontweight="bold")
        fig.text(x + w / 2, CHIP_Y + CHIP_H * 0.28, value, fontsize=9.6,
                 color=NAVY, ha="center", va="center", fontweight="bold")
        x += w + gap


def footnote(fig, text: str = SOURCE_NOTE) -> None:
    fig.text(AX_LEFT, FOOT_Y, text, fontsize=6.8, color=FAINT, va="bottom")


def style_axes(ax, ylabel: str = "", xlabel: str = "") -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.grid(axis="y", color=GRID, linewidth=0.95)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=8, length=0, pad=5)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=8.6, color=MUTED, labelpad=9)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=8.6, color=MUTED, labelpad=8)


def gradient_under(ax, x, y, color: str = BLUE, alpha: float = 0.22) -> None:
    """True gradient fill clipped to the data curve (no white-mask hacks)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = ~np.isnan(y)
    if ok.sum() < 2:
        return
    cmap = LinearSegmentedColormap.from_list("f", ["#FFFFFF", color])
    y0, y1 = ax.get_ylim()
    img = ax.imshow(np.linspace(1, 0, 256).reshape(-1, 1),
                    extent=[x[ok].min(), x[ok].max(), y0, y1],
                    origin="upper", aspect="auto", cmap=cmap, alpha=alpha,
                    zorder=1)
    verts = [(x[ok][0], y0)] + list(zip(x[ok], y[ok])) + [(x[ok][-1], y0)]
    img.set_clip_path(Polygon(verts, closed=True, transform=ax.transData))


def series_line(ax, x, y, color: str = BLUE, label: str = "",
                width: float = 2.0, markers: Optional[bool] = None):
    """Primary series with soft shadow; adds point markers when data is sparse."""
    y = [v if v is not None else math.nan for v in y]
    n_valid = sum(1 for v in y if not (v is None or (isinstance(v, float)
                                                     and math.isnan(v))))
    if markers is None:
        markers = n_valid <= 60
    ln, = ax.plot(x, y, color=color, linewidth=width, solid_capstyle="round",
                  solid_joinstyle="round", label=label, zorder=4,
                  marker="o" if markers else None,
                  markersize=3.4 if markers else 0,
                  markerfacecolor="white", markeredgewidth=1.15,
                  markeredgecolor=color)
    ln.set_path_effects([pe.SimpleLineShadow(offset=(0.5, -0.8), alpha=0.16),
                         pe.Normal()])
    return ln


def limit_line(ax, limit: float, text: str, x_data=None, y_data=None) -> None:
    """Dashed regulatory limit with a pill label placed where it won't collide
    with the data (left or right, whichever side is emptier near the limit)."""
    ax.axhline(limit, color=RED, linewidth=1.4, linestyle=(0, (7, 3)), zorder=5)
    xmin, xmax = ax.get_xlim()
    place_right = True
    if x_data is not None and y_data is not None:
        xs = np.asarray([float(v) for v in x_data], dtype=float)
        ys = np.asarray([np.nan if v is None else float(v) for v in y_data],
                        dtype=float)
        span = (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.14
        near = np.abs(ys - limit) < span
        if near.any():
            mid = (xs.min() + xs.max()) / 2
            place_right = near[xs > mid].sum() <= near[xs <= mid].sum()
    x = xmax if place_right else xmin
    ax.text(x, limit, f" {text} ", color="white", fontsize=7.4,
            fontweight="bold", va="center",
            ha="right" if place_right else "left", zorder=6,
            bbox=dict(boxstyle="round,pad=0.30", facecolor=RED, edgecolor="none"))


def exceedance_fill(ax, x, y, limit: float) -> bool:
    y = np.asarray([np.nan if v is None else float(v) for v in y], dtype=float)
    if not np.any(y > limit):
        return False
    ax.fill_between(x, y, limit, where=(y > limit), color=RED, alpha=0.18,
                    interpolate=True, zorder=3)
    return True


def peak_marker(ax, x, y) -> None:
    y_arr = np.asarray([np.nan if v is None else float(v) for v in y],
                       dtype=float)
    if np.all(np.isnan(y_arr)):
        return
    i = int(np.nanargmax(y_arr))
    ax.scatter([x[i]], [y_arr[i]], s=38, color=NAVY, zorder=7,
               edgecolor="white", linewidth=1.3)
    y0, y1 = ax.get_ylim()
    above = y_arr[i] < y0 + (y1 - y0) * 0.82
    ax.annotate(f"max {y_arr[i]:,.1f}", (x[i], y_arr[i]),
                xytext=(7, 9 if above else -16), textcoords="offset points",
                fontsize=7.8, fontweight="bold", color=NAVY, zorder=7)


def legend_below(ax, handles, ncol: int = 3) -> None:
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0, -0.19),
              ncol=ncol, fontsize=8.2, handlelength=1.8, columnspacing=1.6,
              borderaxespad=0)


def save(fig, out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=DPI)
    plt.close(fig)
    return out_path


def fmt_stats(values: Sequence[Optional[float]]) -> List[tuple]:
    v = [float(x) for x in values if x is not None
         and not (isinstance(x, float) and math.isnan(x))]
    if not v:
        return [("RECORDS", "0")]
    return [("MAX", f"{max(v):,.1f}"), ("MEAN", f"{sum(v)/len(v):,.1f}"),
            ("MIN", f"{min(v):,.1f}"), ("RECORDS", f"{len(v)}")]
