"""Charts for the soil and water report.

Two figures, and only two. The air and noise reports carry a chart per
pollutant because those are time series and the shape of the trace is the
finding. Discrete laboratory results have no shape — the finding is the
number against the limit, and the table already says that. A chart per
parameter here would be twenty-odd bar charts of one bar each.

So: one chart that puts every parameter on a common scale, and one that
proves the soil classification the limits were chosen from.

Colours are computed greys, not a palette. These reports are printed and
photocopied, and a series told apart only by hue disappears the moment it
reaches a monochrome printer.
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from report import chart_theme as T  # noqa: E402

log = logging.getLogger(__name__)

# Four sample series, separated by luminance rather than hue. The steps are
# even in perceived lightness so adjacent bars stay distinguishable in print;
# beyond four samples the series repeat with hatching to keep them apart.
SERIES_GREY: Sequence[str] = ("#1A1A1A", "#5C5C5C", "#949494", "#C8C8C8")
SERIES_HATCH: Sequence[str] = ("", "", "", "", "///", "\\\\\\", "xxx", "...")

# Grain size fractions, coarse to fine.
GRAIN_GREY: Dict[str, str] = {
    "gravel": "#1A1A1A", "sand": "#949494", "mud": "#D2D2D2",
}


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def _short(label: str, width: int = 22) -> str:
    """Trim a long parameter name for the category axis.

    Labels are rotated rather than wrapped. Twelve wrapped two-line labels
    across 155 mm collide into an unreadable band — which is exactly what
    the first render produced.
    """
    text = label.replace("\u2014", "-")
    return text if len(text) <= width else text[:width - 1].rstrip() + "\u2026"


def percent_of_limit_chart(summary, out_dir: str,
                           max_parameters: int = 12) -> Optional[str]:
    """Every parameter on one axis, as a percentage of its own limit.

    Results in a soil report span five orders of magnitude — phenols at
    0.003 mg/kg beside hydrocarbons at 288. Plotted raw, everything except
    the largest is a flat line on the axis. Expressed against its own limit,
    each result says the only thing that matters: how close to the limit it
    came, and whether it went over.

    Parameters with no limit, a minimum, or a range are left out. A minimum
    plotted as a percentage points the wrong way — 40% of a dissolved
    oxygen minimum is a failure and would draw as a short, safe-looking bar.
    Those are in the table; they are not in this chart.
    """
    rows = [r for r in summary.rows if r.get("kind") == "analyte"]
    plottable = []
    for row in rows:
        cells = row.get("cells") or []
        usable = [c for c in cells
                  if c.get("percent_of_limit") is not None
                  and c.get("direction") == "max"]
        if usable:
            plottable.append((row, cells))
    if not plottable:
        log.info("no parameters carry a ceiling limit — chart omitted")
        return None

    # When the suite is long, show the parameters that came closest to their
    # limit. A chart of forty bars is unreadable, and the ones at 2% are not
    # what a reader is looking for.
    def peak(item) -> float:
        return max((c.get("percent_of_limit") or 0.0) for c in item[1])

    plottable.sort(key=peak, reverse=True)
    trimmed = plottable[:max_parameters]
    trimmed.sort(key=lambda item: rows.index(item[0]))

    labels = [_short(r["analyte_name"]) for r, _ in trimmed]
    samples = [s.label for s in summary.samples]
    n_s = max(1, len(samples))

    T.apply_theme()
    width = min(0.8 / n_s, 0.26)
    fig, ax = plt.subplots(figsize=(T.INSERT_W_MM / T.MM_PER_IN, 3.9))

    import numpy as np
    x = np.arange(len(trimmed))
    capped = False
    for i, sample in enumerate(summary.samples):
        heights, hatches = [], []
        for _, cells in trimmed:
            cell = next((c for c in cells
                         if c.get("sample_id") == sample.sample_id), None)
            pct = (cell or {}).get("percent_of_limit")
            if pct is None:
                heights.append(0.0)
            else:
                # A result many times its limit would flatten every other bar
                # on the chart. It is drawn at the ceiling and labelled with
                # its real figure, so the chart stays readable and the number
                # is not misrepresented.
                if pct > 150:
                    capped = True
                    heights.append(150.0)
                else:
                    heights.append(pct)
            hatches.append("")
        offset = (i - (n_s - 1) / 2) * width
        bars = ax.bar(x + offset, heights, width,
                      label=sample.label,
                      color=SERIES_GREY[i % len(SERIES_GREY)],
                      hatch=SERIES_HATCH[i % len(SERIES_HATCH)],
                      edgecolor="#000000", linewidth=0.4)
        for j, (bar, (_, cells)) in enumerate(zip(bars, trimmed)):
            cell = next((c for c in cells
                         if c.get("sample_id") == sample.sample_id), None)
            pct = (cell or {}).get("percent_of_limit")
            if pct is not None and pct > 150:
                ax.text(bar.get_x() + bar.get_width() / 2, 152,
                        f"{pct:.0f}%", ha="center", va="bottom",
                        fontsize=6.5, rotation=90, color=T.INK)

    ax.axhline(100, color="#000000", linewidth=1.2, linestyle="--")
    ax.text(len(trimmed) - 0.4, 103, "Applicable limit", fontsize=7.5,
            ha="right", color=T.INK)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7.5, rotation=40, ha="right",
                       rotation_mode="anchor")
    ax.set_ylim(0, 165 if capped else 125)
    T.style_axes(ax, ylabel="Result as % of applicable limit")
    T.nice_yaxis(ax)
    ax.legend(frameon=False, ncol=min(n_s, 6), loc="upper left", fontsize=8)

    if capped:
        T.footnote(fig, "Bars are capped at 150%; results above that are "
                        "labelled with their actual value.")
    else:
        T.footnote(fig, "Parameters with no limit, or judged against a "
                        "minimum or a range, are reported in the tables only.")

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "percent_of_limit.png")
    fig.tight_layout()
    fig.savefig(path, dpi=T.DPI)
    plt.close(fig)
    return path


def grain_size_chart(summary, out_dir: str) -> Optional[str]:
    """Gravel, sand and mud by sample.

    Not decoration. Article (1) of the soil regulation splits soil at 75 µm,
    and that split chooses which half of the limit table applies. The chart
    shows the classification rather than asserting it, so a reader can see
    the basis for every limit in the report.
    """
    keys = ("gravel", "sand", "mud")
    present = {k: {} for k in keys}
    for cell in summary.cells:
        if cell.analyte_key in keys and cell.value is not None:
            present[cell.analyte_key][cell.sample_label] = cell.value
    if not any(present[k] for k in keys):
        return None

    labels = [s.label for s in summary.samples]
    labels = [lb for lb in labels
              if any(lb in present[k] for k in keys)]
    if not labels:
        return None

    T.apply_theme()
    fig, ax = plt.subplots(figsize=(T.INSERT_W_MM / T.MM_PER_IN,
                                    1.0 + 0.42 * len(labels)))
    import numpy as np
    left = np.zeros(len(labels))
    for key in keys:
        vals = np.array([present[key].get(lb, 0.0) for lb in labels],
                        dtype=float)
        if not vals.any():
            continue
        ax.barh(labels, vals, left=left, height=0.55,
                label=key.capitalize(), color=GRAIN_GREY[key],
                edgecolor="#000000", linewidth=0.4)
        left = left + vals

    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    T.style_axes(ax, xlabel="Percentage by mass")
    ax.legend(frameon=False, ncol=3, loc="lower right",
              bbox_to_anchor=(1.0, 1.0), fontsize=8)

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "grain_size.png")
    fig.tight_layout()
    fig.savefig(path, dpi=T.DPI)
    plt.close(fig)
    return path


def generate_sample_charts(summary, out_dir: str) -> Dict[str, str]:
    """Both figures, each omitted rather than drawn empty.

    A failed chart never fails the report. A report with one figure missing
    is still a correct report; a report that would not generate because a
    chart raised is not.
    """
    figs: Dict[str, str] = {}
    for name, fn in (("percent_of_limit", percent_of_limit_chart),
                     ("grain_size", grain_size_chart)):
        try:
            path = fn(summary, out_dir)
            if path:
                figs[name] = path
        except Exception:  # noqa: BLE001
            log.warning("chart %s failed — omitted from the report", name,
                        exc_info=True)
    return figs
