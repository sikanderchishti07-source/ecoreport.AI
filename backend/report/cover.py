# -*- coding: utf-8 -*-
"""Cover artwork for the report — hero band and value-proposition icons.

The hero band is rendered per report so the project name is set at the right
size and the operator's own station photograph can be used as the backdrop.

Composition, back to front:

  1. the photograph, filling the whole band;
  2. a light panel over the left, its right edge stepping down in two
     segments until it meets the main diagonal;
  3. one continuous diagonal from the left edge down to the lower right, a
     thin green strip riding above it and a navy triangle below;
  4. a dot texture on the thick part of the navy, a green wedge at the far
     bottom right;
  5. the type: eyebrow, rule, three-line title, tagline, and the location pin
     with the project name and sub-location on the navy.

Every coordinate is a fraction of the canvas, so the band re-renders at any
size without the layout drifting. The project name is measured against the
navy's own edge and stepped down until it fits — the triangle narrows as it
rises, so a long site name that would sit comfortably at the foot of the band
runs off the colour higher up.

Text is drawn with the report's display font; Arabic is reshaped and
bidi-ordered so it renders correctly in the image.
"""
from __future__ import annotations

import logging
import os
import textwrap
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Circle, Polygon, Wedge

log = logging.getLogger(__name__)

NAVY = "#12315B"
NAVY_DEEP = "#0C2444"
GREEN = "#4FA23F"
GREEN_DARK = "#41903A"
WHITE = "#FFFFFF"
PANEL = "#F7F9FB"
INK_SUB = "#3C4A5A"
PALE = "#C9D8E8"

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

HERO_W, HERO_H = 2100, 1580
ICON_PX = 320

# --- the main diagonal: height DIAG_L at x = 0, reaching 0 at x = DIAG_X ---
DIAG_L = 0.262
DIAG_X = 0.710

# Safe margin, as a fraction of the canvas. No text, pin or caption is drawn
# outside it, so the band survives being placed at a width that does not match
# its own aspect ratio without anything being trimmed at the paper edge. The
# colour blocks still bleed to the edge, which is what the design calls for.
PAD_L = 0.078
PAD_R = 0.055


def _font(bold: bool = False, arabic: bool = False) -> dict:
    have = {f.name for f in fm.fontManager.ttflist}
    order = (["Amiri", "Noto Sans Arabic"] if arabic
             else ["IBM Plex Sans", "Inter", "Noto Sans", "DejaVu Sans"])
    for n in order:
        if n in have:
            return {"fontname": n, "fontweight": "bold" if bold else "normal"}
    return {"fontweight": "bold" if bold else "normal"}


def _shape_ar(text: str) -> str:
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:  # noqa: BLE001
        return text


def _backdrop(ax, photo_path: Optional[str]) -> bool:
    """The campaign's photograph; a neutral graphic when none is supplied."""
    if not (photo_path and os.path.exists(photo_path)):
        default = os.path.join(ASSETS, "hero_default.png")
        photo_path = default if os.path.exists(default) else None
    if photo_path:
        try:
            img = plt.imread(photo_path)
            ih, iw = img.shape[:2]
            target = HERO_W / HERO_H
            if iw / ih > target:
                nw = int(ih * target)
                x0 = int((iw - nw) * 0.62)       # favour the right of frame
                img = img[:, x0:x0 + nw]
            else:
                nh = int(iw / target)
                y0 = int((ih - nh) * 0.28)
                img = img[y0:y0 + nh, :]
            ax.imshow(img, extent=[0, HERO_W, 0, HERO_H], aspect="auto",
                      zorder=1)
            return True
        except Exception:  # noqa: BLE001
            log.warning("cover photo unreadable, using graphic", exc_info=True)

    sky = LinearSegmentedColormap.from_list(
        "sky", ["#8FB6D4", "#B7D0E3", "#D6E4EF", "#EDF3F8"])
    ax.imshow(np.linspace(1, 0, 256).reshape(-1, 1),
              extent=[0, HERO_W, 0, HERO_H], origin="upper", aspect="auto",
              cmap=sky, zorder=1)
    rng = np.random.default_rng(11)
    base = HERO_H * 0.14
    for _ in range(30):
        x = rng.uniform(HERO_W * 0.38, HERO_W)
        ax.add_patch(plt.Rectangle((x, base), rng.uniform(40, 120),
                                   rng.uniform(140, 620), facecolor="#7FA4C2",
                                   alpha=0.45, edgecolor="none", zorder=2))
    xs = np.linspace(HERO_W * 0.30, HERO_W, 260)
    tops = base + 60 + 26 * np.sin(xs / 70)
    ax.fill_between(xs, base - 60, tops, color="#3D7A50", alpha=0.85, zorder=3)
    return False


def _dots(ax, W: float, H: float) -> None:
    """Faint dot grid on the thick part of the navy."""
    for i in range(4):
        for j in range(4):
            x = W * (0.020 + i * 0.014)
            y = H * (0.038 + j * 0.030)
            if y < DIAG_L * H * (1 - x / (DIAG_X * W)) - H * 0.03:
                ax.add_patch(Circle((x, y), W * 0.0021, facecolor="#4C6C97",
                                    edgecolor="none", zorder=7))


def _navy_right(y_frac: float) -> float:
    """x (as a fraction of width) where the navy ends at the given height."""
    if y_frac >= DIAG_L:
        return 0.0
    return DIAG_X * (1.0 - y_frac / DIAG_L)


def _fit_text(fig, ax, x, y_frac, text, colour, max_fs, bold, ar, W, H,
              pad: float = 0.030):
    """Draw text guaranteed to stay inside the navy.

    The band narrows as it rises, so a project name that fits at the foot of
    the band would run onto the photograph higher up. Measure, then step the
    size down until it fits, rather than trusting a fixed point size.
    """
    # never run past the navy's own edge, and never past the safe margin
    limit = min(_navy_right(y_frac) - pad, 1.0 - PAD_R) * W - x
    if limit <= 0:
        limit = W * 0.25
    fs = max_fs
    while fs > 9:
        t = ax.text(x, y_frac * H, text, color=colour, fontsize=fs,
                    va="center", zorder=9, **_font(bold, ar))
        fig.canvas.draw()
        if t.get_window_extent(fig.canvas.get_renderer()).width <= limit:
            return t
        t.remove()
        fs -= 1
    return ax.text(x, y_frac * H, text, color=colour, fontsize=9,
                   va="center", zorder=9, **_font(bold, ar))


def build_hero(project_name: str, out_path: str,
               photo_path: Optional[str] = None, lang: str = "en",
               site_line: Optional[str] = None) -> str:
    """Render the cover hero band."""
    ar = lang == "ar"
    fig = plt.figure(figsize=(HERO_W / 200, HERO_H / 200), dpi=200)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, HERO_W)
    ax.set_ylim(0, HERO_H)
    ax.axis("off")
    W, H = HERO_W, HERO_H

    _backdrop(ax, photo_path)

    # light panel — its foot rides the same line as the top of the green
    # strip, so no sliver of photograph shows between them
    ax.add_patch(Polygon([(0, H), (W * 0.638, H), (W * 0.598, H * 0.615),
                          (W * 0.430, H * 0.137), (0, H * 0.295)],
                         closed=True, facecolor=PANEL, edgecolor="none",
                         zorder=4))

    t = H * 0.033
    ax.add_patch(Polygon([(0, DIAG_L * H + t), (W * 0.470, H * 0.089 + t),
                          (W * 0.470, H * 0.089), (0, DIAG_L * H)],
                         closed=True, facecolor=GREEN, edgecolor="none",
                         zorder=5))

    ax.add_patch(Polygon([(0, DIAG_L * H), (W * DIAG_X, 0), (0, 0)],
                         closed=True, facecolor=NAVY, edgecolor="none",
                         zorder=6))
    _dots(ax, W, H)

    ax.add_patch(Polygon([(W * 0.860, 0), (W, 0), (W, H * 0.105)],
                         closed=True, facecolor=GREEN, alpha=0.95,
                         edgecolor="none", zorder=6))

    L = W * PAD_L

    eyebrow = "الهواء المحيط" if ar else "AMBIENT AIR QUALITY"
    ax.text(L, H * 0.876, _shape_ar(eyebrow) if ar else eyebrow,
            color=GREEN_DARK, fontsize=17.5, va="center", zorder=9,
            **_font(True, ar))
    ax.plot([L, L + W * 0.030], [H * 0.822, H * 0.822], color=NAVY, lw=5,
            solid_capstyle="butt", zorder=9)

    title = (["تقرير رصد", "جودة الهواء"] if ar
             else ["AIR QUALITY", "MONITORING", "REPORT"])
    for i, line in enumerate(title):
        ax.text(L, H * (0.745 - i * 0.104), _shape_ar(line) if ar else line,
                color=NAVY, fontsize=46, va="center", zorder=9,
                **_font(True, ar))

    tag = ([("رصد دقيق.", INK_SUB), ("نتائج موثوقة.", INK_SUB),
            ("بيئة أكثر صحة.", GREEN_DARK)] if ar else
           [("Accurate Monitoring.", INK_SUB), ("Reliable Results.", INK_SUB),
            ("Healthier Environment.", GREEN_DARK)])
    for i, (line, colour) in enumerate(tag):
        ax.text(L, H * (0.447 - i * 0.050), _shape_ar(line) if ar else line,
                color=colour, fontsize=19.5, va="center", zorder=9,
                **_font(False, ar))

    # location pin
    px, py = W * 0.082, H * 0.098
    r = W * 0.0185
    ax.add_patch(Circle((px, py + r * 0.35), r, facecolor="none",
                        edgecolor=GREEN, lw=4.2, zorder=9))
    ax.add_patch(Circle((px, py + r * 0.45), r * 0.34, facecolor=GREEN,
                        edgecolor="none", zorder=10))
    ax.plot([px, px], [py - r * 0.62, py - r * 1.55], color=GREEN, lw=4.2,
            solid_capstyle="round", zorder=9)

    name = (project_name or "").upper()
    lines = textwrap.wrap(name, width=18)[:2] or [""]
    tx = W * 0.126
    ys = (0.132, 0.088) if len(lines) > 1 else (0.115,)
    for line, yf in zip(lines, ys):
        _fit_text(fig, ax, tx, yf, _shape_ar(line) if ar else line,
                  WHITE, 20, True, ar, W, H)
    if site_line:
        _fit_text(fig, ax, tx, 0.042 if len(lines) > 1 else 0.062,
                  _shape_ar(site_line) if ar else site_line,
                  PALE, 16, False, ar, W, H)

    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# Value-proposition icons (drawn once, cached in assets/)
# ---------------------------------------------------------------------------
def _icon_canvas():
    fig = plt.figure(figsize=(ICON_PX / 200, ICON_PX / 200), dpi=200)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    ax.add_patch(Circle((50, 50), 46, facecolor=NAVY, edgecolor="none"))
    return fig, ax


def _icon_accurate(ax):
    for r, c in ((26, WHITE), (18, NAVY), (10, WHITE)):
        ax.add_patch(Circle((50, 50), r, facecolor=c, edgecolor="none"))
    ax.add_patch(Circle((50, 50), 4.5, facecolor=NAVY, edgecolor="none"))
    ax.plot([50, 76], [50, 74], color=WHITE, lw=4, solid_capstyle="round")


def _icon_reliable(ax):
    shield = [[50, 80], [26, 68], [26, 42], [50, 24], [74, 42], [74, 68]]
    ax.add_patch(Polygon(shield, closed=True, facecolor=WHITE, edgecolor="none"))
    ax.plot([38, 47, 64], [52, 42, 63], color=NAVY, lw=6.5,
            solid_capstyle="round", solid_joinstyle="round")


def _icon_compliant(ax):
    for i, h in enumerate((18, 28, 38)):
        ax.add_patch(plt.Rectangle((32 + i * 13, 30), 9, h, facecolor=WHITE,
                                   edgecolor="none"))
    ax.plot([32, 45, 58, 72], [56, 46, 62, 74], color=GREEN, lw=4.5,
            solid_capstyle="round")
    ax.scatter([72], [74], s=60, color=GREEN, zorder=5)


def _icon_sustainable(ax):
    ax.add_patch(Circle((50, 50), 27, facecolor="none", edgecolor=WHITE, lw=4))
    ax.plot([23, 77], [50, 50], color=WHITE, lw=3)
    for w in (14, 26):
        ax.add_patch(Wedge((50, 50), 27, 90 - 0, 90 + 0, width=0))
    th = np.linspace(-np.pi / 2, np.pi / 2, 60)
    for k in (0.5, 1.0):
        ax.plot(50 + 27 * k * np.cos(th) * 0.55, 50 + 27 * np.sin(th),
                color=WHITE, lw=2.6)
        ax.plot(50 - 27 * k * np.cos(th) * 0.55, 50 + 27 * np.sin(th),
                color=WHITE, lw=2.6)
    leaf = [[50, 34], [62, 44], [50, 56], [40, 44]]
    ax.add_patch(Polygon(leaf, closed=True, facecolor=GREEN, edgecolor="none"))


ICONS = {
    "accurate": _icon_accurate,
    "reliable": _icon_reliable,
    "compliant": _icon_compliant,
    "sustainable": _icon_sustainable,
}


def build_icons(dest_dir: str = ASSETS, force: bool = False) -> dict:
    """Draw the four value-prop icons once; reuse thereafter."""
    os.makedirs(dest_dir, exist_ok=True)
    out = {}
    for name, draw in ICONS.items():
        path = os.path.join(dest_dir, f"icon_{name}.png")
        if force or not os.path.exists(path):
            fig, ax = _icon_canvas()
            draw(ax)
            fig.savefig(path, dpi=200, transparent=True)
            plt.close(fig)
        out[name] = path
    return out


if __name__ == "__main__":
    build_icons(force=True)
    build_hero("Sample Project", os.path.join(HERE, "assets", "_hero_demo.png"),
               site_line="Sample Site")
    print("cover artwork built")
