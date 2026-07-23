"""Cover artwork for the report — hero band and value-proposition icons.

The hero band is rendered per report so the project name is baked in at the
right size and the operator's own station photograph can be used. When no
photo is supplied an abstract air-flow graphic is drawn instead, so a cover
never looks unfinished.

Text inside the hero is drawn with the report's display font; Arabic is
reshaped and bidi-ordered so it renders correctly in the image.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Circle, Polygon, Wedge

log = logging.getLogger(__name__)

NAVY = "#123A63"
NAVY_DEEP = "#0C2C4D"
GREEN = "#4CA64C"
GREEN_DARK = "#2F7D32"
GOLD = "#C9A227"
WHITE = "#FFFFFF"

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

HERO_W, HERO_H = 2100, 1180          # ~155 mm wide at print resolution
ICON_PX = 320


def _font(bold: bool = False, arabic: bool = False) -> dict:
    names = ({"Amiri", "Noto Sans Arabic"} if arabic
             else {"IBM Plex Sans", "Inter", "Noto Sans", "DejaVu Sans"})
    have = {f.name for f in fm.fontManager.ttflist}
    for n in (["Amiri", "Noto Sans Arabic"] if arabic else
              ["IBM Plex Sans", "Inter", "Noto Sans", "DejaVu Sans"]):
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



def _draw_skyline(ax) -> None:
    """Vector Riyadh-style skyline used when no photograph is supplied:
    daylight sky, layered towers, a treeline, and a monitoring sensor on its
    mast at the right — the same composition as a station photo."""
    # sky
    sky = LinearSegmentedColormap.from_list(
        "sky", ["#1B4E7E", "#3E82B8", "#8FC0DF", "#CFE3F1"])
    ax.imshow(np.linspace(1, 0, 256).reshape(-1, 1),
              extent=[0, HERO_W, 0, HERO_H], origin="upper", aspect="auto",
              cmap=sky, zorder=1)

    rng = np.random.default_rng(5)
    base = HERO_H * 0.20

    def tower(x, w, h, colour, alpha):
        ax.add_patch(plt.Rectangle((x, base), w, h, facecolor=colour,
                                   alpha=alpha, edgecolor="none", zorder=2))

    # far haze layer
    for _ in range(22):
        x = rng.uniform(HERO_W * 0.30, HERO_W)
        tower(x, rng.uniform(38, 92), rng.uniform(90, 300), "#7FA9CB", .55)

    # mid layer
    for _ in range(16):
        x = rng.uniform(HERO_W * 0.34, HERO_W * 0.99)
        tower(x, rng.uniform(46, 104), rng.uniform(140, 400), "#5E8CB4", .75)

    # landmark 1 — tall tower with an open arch near the crown
    lx, lw = HERO_W * 0.615, 150
    lh = HERO_H * 0.60
    tower(lx, lw, lh, "#44749E", .95)
    ax.add_patch(plt.Rectangle((lx + lw * 0.22, base + lh * 0.80),
                               lw * 0.56, lh * 0.13, facecolor="#9CC3DF",
                               alpha=.95, edgecolor="none", zorder=3))
    ax.add_patch(Polygon([[lx, base + lh], [lx + lw, base + lh],
                          [lx + lw * 0.72, base + lh * 1.10],
                          [lx + lw * 0.28, base + lh * 1.10]],
                         closed=True, facecolor="#44749E", alpha=.95, zorder=3))

    # landmark 2 — slender tower with a spire and orb
    sx, sw = HERO_W * 0.745, 96
    sh = HERO_H * 0.50
    ax.add_patch(Polygon([[sx, base], [sx + sw, base],
                          [sx + sw * 0.62, base + sh],
                          [sx + sw * 0.38, base + sh]],
                         closed=True, facecolor="#3F6E96", alpha=.95, zorder=3))
    ax.add_patch(Circle((sx + sw * 0.5, base + sh * 1.06), 22,
                        facecolor="#B9D6EA", alpha=.95, zorder=4))
    ax.plot([sx + sw * 0.5, sx + sw * 0.5],
            [base + sh * 1.10, base + sh * 1.30], color="#B9D6EA", lw=3,
            zorder=4)

    # near layer
    for _ in range(12):
        x = rng.uniform(HERO_W * 0.36, HERO_W * 0.98)
        tower(x, rng.uniform(54, 118), rng.uniform(110, 260), "#2F5D86", .92)

    # treeline
    xs = np.linspace(HERO_W * 0.28, HERO_W, 260)
    tops = base + 34 + 16 * np.sin(xs / 55) + 10 * np.sin(xs / 23 + 1.3)
    ax.fill_between(xs, base - 30, tops, color="#2E6B4A", alpha=.95, zorder=5)
    ax.fill_between(xs, base - 30, tops - 16, color="#24583C", alpha=.9,
                    zorder=5)

    # ---- monitoring sensor on its mast, right-hand side ----
    mx = HERO_W * 0.885
    ax.add_patch(plt.Rectangle((mx - 9, base - 40), 18, HERO_H * 0.46,
                               facecolor="#C9CFD4", edgecolor="#8A9298",
                               lw=1.2, zorder=6))
    top_y = base - 40 + HERO_H * 0.46
    # radiation-shield plates
    for k in range(7):
        w = 96 - k * 5
        y = top_y + k * 17
        ax.add_patch(plt.Rectangle((mx - w / 2, y), w, 11,
                                   facecolor="#E4E8EB", edgecolor="#9AA2A8",
                                   lw=1.0, zorder=7))
    ax.add_patch(Circle((mx, top_y + 7 * 17 + 22), 26, facecolor="#EDF0F2",
                        edgecolor="#9AA2A8", lw=1.2, zorder=7))
    # analyser enclosure
    ax.add_patch(plt.Rectangle((mx - 62, base + HERO_H * 0.10), 124,
                               HERO_H * 0.20, facecolor="#DDE2E6",
                               edgecolor="#9AA2A8", lw=1.4, zorder=7))
    ax.add_patch(plt.Rectangle((mx - 44, base + HERO_H * 0.155), 88,
                               HERO_H * 0.075, facecolor="#C4CBD1",
                               alpha=.8, edgecolor="none", zorder=8))
    # inlet tube curving down
    tt = np.linspace(0, 1, 60)
    ax.plot(mx + 62 + 40 * np.sin(tt * 2.1), base + HERO_H * 0.12 - tt * 150,
            color="#6E767D", lw=5, solid_capstyle="round", zorder=8)


def build_hero(project_name: str, out_path: str,
               photo_path: Optional[str] = None, lang: str = "en") -> str:
    """Render the cover hero band: imagery, gradient scrim, title, tagline."""
    ar = lang == "ar"
    fig = plt.figure(figsize=(HERO_W / 200, HERO_H / 200), dpi=200)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, HERO_W)
    ax.set_ylim(0, HERO_H)
    ax.axis("off")

    # ---- background: the campaign's own photo wins; otherwise the bundled
    # station/skyline photograph; otherwise a drawn illustration ----
    used_photo = False
    if not (photo_path and os.path.exists(photo_path)):
        default_hero = os.path.join(ASSETS, "hero_default.png")
        if os.path.exists(default_hero):
            photo_path = default_hero
    if photo_path and os.path.exists(photo_path):
        try:
            img = plt.imread(photo_path)
            ih, iw = img.shape[:2]
            target = HERO_W / HERO_H
            if iw / ih > target:                     # crop sides
                new_w = int(ih * target)
                x0 = (iw - new_w) // 2
                img = img[:, x0:x0 + new_w]
            else:                                    # crop top/bottom
                new_h = int(iw / target)
                y0 = int((ih - new_h) * 0.35)
                img = img[y0:y0 + new_h, :]
            ax.imshow(img, extent=[0, HERO_W, 0, HERO_H], aspect="auto",
                      zorder=1)
            used_photo = True
        except Exception:  # noqa: BLE001
            log.warning("cover photo unreadable, using graphic", exc_info=True)

    if not used_photo:
        _draw_skyline(ax)

    # ---- scrim so text always reads, whatever the photo ----
    scrim = LinearSegmentedColormap.from_list(
        "s", [(0.05, 0.18, 0.31, 0.94), (0.05, 0.18, 0.31, 0.86),
              (0.05, 0.18, 0.31, 0.30), (0.05, 0.18, 0.31, 0.06)])
    ax.imshow(np.linspace(0, 1, 256).reshape(1, -1),
              extent=[0, HERO_W, 0, HERO_H], aspect="auto", cmap=scrim,
              zorder=4)

    # ---- text block ----
    L = HERO_W * 0.055
    eyebrow = "الهواء المحيط" if ar else "AMBIENT AIR QUALITY"
    t1 = "تقرير رصد" if ar else "AIR QUALITY"
    t2 = "جودة الهواء" if ar else "MONITORING REPORT"
    tag1 = "رصد دقيق · نتائج موثوقة" if ar else "Accurate Monitoring. Reliable Results."
    tag2 = "بيئة أكثر صحة" if ar else "Healthier Environment."
    if ar:
        eyebrow, t1, t2, tag1, tag2 = map(_shape_ar, (eyebrow, t1, t2, tag1, tag2))

    ax.text(L, HERO_H * 0.795, eyebrow, color="#7FD08A", fontsize=15,
            zorder=6, **_font(True, ar))
    ax.text(L, HERO_H * 0.665, t1, color=WHITE, fontsize=44, zorder=6,
            **_font(True, ar))
    ax.text(L, HERO_H * 0.545, t2, color=WHITE, fontsize=44, zorder=6,
            **_font(True, ar))
    ax.plot([L, L + HERO_W * 0.085], [HERO_H * 0.475, HERO_H * 0.475],
            color=GREEN, lw=7, solid_capstyle="round", zorder=6)
    ax.text(L, HERO_H * 0.365, tag1, color="#DCE7F2", fontsize=15.5, zorder=6,
            **_font(False, ar))
    ax.text(L, HERO_H * 0.295, tag2, color="#DCE7F2", fontsize=15.5, zorder=6,
            **_font(False, ar))
    if project_name:
        pn = _shape_ar(project_name) if ar else project_name
        ax.text(L, HERO_H * 0.175, pn, color="#9FC3E3", fontsize=17, zorder=6,
                **_font(True, ar))

    # ---- curved white sweep along the bottom edge ----
    xs = np.linspace(0, HERO_W, 400)
    curve = HERO_H * 0.075 + HERO_H * 0.075 * np.sin(xs / HERO_W * np.pi * 1.15
                                                     - 0.4)
    ax.fill_between(xs, 0, curve, color=WHITE, zorder=7)
    ax.plot(xs, curve, color=GREEN, lw=4, zorder=8)

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
    build_hero("Sample Project", os.path.join(HERE, "assets", "_hero_demo.png"))
    print("cover artwork built")
