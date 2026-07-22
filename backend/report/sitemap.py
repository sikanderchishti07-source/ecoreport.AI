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
                     labels: List[str], out_path: str) -> Optional[str]:
    """Wind rose petals drawn over the satellite map at the station point,
    matching the WRPLOT-style composite used in the gold-standard report."""
    if not map_path or not os.path.exists(map_path):
        return None
    try:
        img = plt.imread(map_path)
        h, w = img.shape[:2]
        T.apply_theme()
        fig = plt.figure(figsize=(T.ROSE_W, T.ROSE_W * h / w))
        base = fig.add_axes([0, 0, 1, 1])
        base.imshow(img)
        base.axis("off")

        # transparent polar overlay anchored on the station (image centre)
        pol = fig.add_axes([0.18, 0.16, 0.64, 0.68], projection="polar",
                           facecolor="none")
        pol.set_theta_zero_location("N")
        pol.set_theta_direction(-1)
        theta = np.deg2rad(np.arange(0, 360, 22.5))
        width = np.deg2rad(20.5)
        bottom = np.zeros(16)
        for i, f in enumerate(freqs):
            pol.bar(theta, f, width=width, bottom=bottom,
                    color=T.ROSE_SCALE[i % len(T.ROSE_SCALE)], alpha=0.88,
                    edgecolor="white", linewidth=0.9, zorder=3,
                    label=labels[i] if i < len(labels) else None)
            bottom += f
        pol.set_xticks([])
        pol.set_yticks([])
        pol.grid(False)
        pol.spines["polar"].set_visible(False)
        pol.patch.set_alpha(0)
        fig.savefig(out_path, dpi=T.DPI)
        plt.close(fig)
        return out_path
    except Exception:  # noqa: BLE001
        log.exception("wind rose overlay failed")
        return None
