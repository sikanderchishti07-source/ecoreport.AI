"""Figure 1 — satellite site map, and Figure 19b — wind rose over the map.

Uses the Google Static Maps API (set GOOGLE_MAPS_API_KEY in the backend
environment). If the key is missing or the request fails, the report falls
back to an operator-uploaded site map, and if there is none, the figure is
simply omitted — a report is never blocked by a map.
"""
from __future__ import annotations

import logging
import math
import os
from typing import List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import numpy as np

from report import chart_theme as T

log = logging.getLogger(__name__)

API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
STATIC_URL = "https://maps.googleapis.com/maps/api/staticmap"


def fetch_site_map(lat: float, lon: float, out_path: str, zoom: int = 17,
                   size: str = "640x600", scale: int = 2,
                   label: str = "AAQMS") -> Optional[str]:
    """Satellite tile centred on the station with a labelled marker."""
    if not API_KEY:
        log.info("GOOGLE_MAPS_API_KEY not set — skipping automatic site map")
        return None
    try:
        import requests
        params = {
            "center": f"{lat},{lon}",
            "zoom": zoom,
            "size": size,
            "scale": scale,
            "maptype": "satellite",
            "markers": f"color:red|label:A|{lat},{lon}",
            "key": API_KEY,
        }
        r = requests.get(STATIC_URL, params=params, timeout=25)
        r.raise_for_status()
        if not r.headers.get("content-type", "").startswith("image"):
            log.warning("static map returned non-image: %s", r.text[:200])
            return None
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as fh:
            fh.write(r.content)
        return _annotate(out_path, out_path, label, lat, lon)
    except Exception:  # noqa: BLE001
        log.exception("site map fetch failed")
        return None


def _annotate(src: str, out_path: str, label: str, lat: float,
              lon: float) -> str:
    """Add the station label, north arrow, scale note and attribution."""
    img = plt.imread(src)
    h, w = img.shape[:2]
    T.apply_theme()
    fig = plt.figure(figsize=(T.FIG_W, T.FIG_W * h / w))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(img)
    ax.axis("off")

    ax.annotate(label, xy=(w / 2, h / 2), xytext=(w / 2 + w * 0.06,
                                                  h / 2 - h * 0.10),
                fontsize=9, fontweight="bold", color="white",
                bbox=dict(boxstyle="round,pad=0.32", fc=T.NAVY, ec="white",
                          lw=1.0),
                arrowprops=dict(arrowstyle="-|>", color="white", lw=1.4))
    ax.annotate("N", xy=(w * 0.94, h * 0.10), ha="center", fontsize=10,
                fontweight="bold", color="white")
    ax.annotate("", xy=(w * 0.94, h * 0.055), xytext=(w * 0.94, h * 0.125),
                arrowprops=dict(arrowstyle="-|>", color="white", lw=1.6))
    ax.text(w * 0.02, h * 0.975, f"{lat:.6f} N, {lon:.6f} E   ·   "
            f"Imagery © Google", fontsize=6.6, color="white", va="bottom",
            bbox=dict(boxstyle="round,pad=0.25", fc=(0, 0, 0, 0.45), ec="none"))
    fig.savefig(out_path, dpi=T.DPI)
    plt.close(fig)
    return out_path


def wind_rose_on_map(map_path: str, freqs: List[np.ndarray],
                     labels: List[str], out_path: str,
                     records: Optional[int] = None,
                     prevailing: Optional[str] = None) -> Optional[str]:
    """Wind rose drawn over the satellite map at the station point.

    The standalone polar chart already carries the exact scale, so an overlay
    that showed direction alone would be decorative. This one keeps the speed
    bands and adds labelled percentage rings, so the reader can measure
    frequency against the terrain rather than judge it by petal length.

    Title and legend sit on solid plates: satellite imagery is unpredictable,
    and white text on a bright sand tile is unreadable.
    """
    if not map_path or not os.path.exists(map_path):
        return None
    try:
        img = plt.imread(map_path)
        h, w = img.shape[:2]
        T.apply_theme()
        fig = plt.figure(figsize=(T.FIG_W, T.FIG_W * h / w))
        base = fig.add_axes([0, 0, 1, 1])
        base.imshow(img)
        base.set_xlim(0, w)
        base.set_ylim(h, 0)
        base.axis("off")

        pol = fig.add_axes([0.19, 0.19, 0.62, 0.62], projection="polar",
                           facecolor="none")
        pol.set_theta_zero_location("N")
        pol.set_theta_direction(-1)
        theta = np.deg2rad(np.arange(0, 360, 22.5))
        width = np.deg2rad(19.5)

        shades = [T.ROSE_SCALE[max(0, len(T.ROSE_SCALE) - len(freqs) + i)]
                  for i in range(len(freqs))] if freqs else []
        bottom = np.zeros(16)
        for i, f in enumerate(freqs):
            pol.bar(theta, f, width=width, bottom=bottom,
                    color=shades[i] if i < len(shades) else T.NAVY,
                    alpha=0.88, edgecolor="white", linewidth=1.4, zorder=4)
            bottom += np.asarray(f)

        # percentage rings, so the overlay can actually be read
        top = float(bottom.max()) if bottom.size else 0.0
        if top > 0:
            for r in np.linspace(top / 3.0, top, 3):
                pol.plot(np.linspace(0, 2 * np.pi, 200), [r] * 200,
                         color="white", lw=0.9, alpha=0.75, zorder=6)
                pol.text(np.deg2rad(112), r, f"{r:.0f}%", color="white",
                         fontsize=8.5, ha="center", va="bottom", zorder=7,
                         bbox=dict(boxstyle="round,pad=0.15", fc=T.NAVY,
                                   ec="none", alpha=0.85))
            pol.set_ylim(0, top * 1.05)

        pol.set_xticks([])
        pol.set_yticks([])
        pol.grid(False)
        pol.spines["polar"].set_visible(False)
        for lbl, ang in (("N", 90), ("E", 0), ("S", 270), ("W", 180)):
            pol.text(np.deg2rad((90 - ang) % 360), pol.get_ylim()[1] * 1.13,
                     lbl, ha="center", va="center", color="white",
                     fontsize=10, fontweight="bold", zorder=7,
                     bbox=dict(boxstyle="circle,pad=0.22", fc=T.NAVY,
                               ec="white", lw=1))

        # title plate
        base.add_patch(plt.Rectangle((0, 0), w, h * 0.088, facecolor=T.NAVY,
                                     alpha=0.9, zorder=8))
        base.text(w * 0.03, h * 0.030, "WIND ROSE", color="white",
                  fontsize=12.5, fontweight="bold", va="center", zorder=9)
        sub = []
        if records:
            sub.append(f"{records} valid hourly records")
        if prevailing:
            sub.append(f"prevailing {prevailing}")
        if sub:
            base.text(w * 0.03, h * 0.064, " \u00b7 ".join(sub),
                      color="#C9D8E8", fontsize=8.5, va="center", zorder=9)

        # legend plate
        base.add_patch(plt.Rectangle((0, h * 0.928), w, h * 0.072,
                                     facecolor=T.NAVY, alpha=0.9, zorder=8))
        x = w * 0.03
        for i, lab in enumerate(labels[:len(freqs)]):
            base.add_patch(plt.Rectangle((x, h * 0.950), w * 0.030, h * 0.028,
                                         facecolor=shades[i] if i < len(shades)
                                         else T.NAVY,
                                         edgecolor="white", lw=1.1, zorder=9))
            base.text(x + w * 0.042, h * 0.964, f"{lab} m/s", color="white",
                      fontsize=9, va="center", zorder=9)
            x += w * 0.26

        # station marker
        base.add_patch(Circle((w / 2, h / 2), max(w, h) * 0.011,
                              facecolor="#C0392B", edgecolor="white",
                              lw=2.2, zorder=10))
        base.text(w / 2 + w * 0.022, h / 2 - h * 0.018, "AAQMS", color="white",
                  fontsize=10.5, fontweight="bold", zorder=10,
                  bbox=dict(boxstyle="round,pad=0.28", fc=T.NAVY, ec="none"))

        fig.savefig(out_path, dpi=T.DPI)
        plt.close(fig)
        return out_path
    except Exception:  # noqa: BLE001
        log.exception("wind rose overlay failed")
        return None
