# -*- coding: utf-8 -*-
"""Render a report cover as a single full-bleed A4 plate.

Named ``cover_plate`` and not ``cover`` because ``report/cover.py`` already
exists and builds the old hero band and the value-proposition icons.

One module serves both report types. The noise cover and the air cover share
their geometry, their type and their fitting rules, and differ only in what
they switch on: the air cover adds a strip of four value pillars and a
contact bar, and turns the green stripe off. Keeping them in one renderer is
what stops the two covers drifting apart as either is adjusted.

The whole cover — photograph, geometry, logo and every line of wording — is
drawn here with Pillow and returned as one 300 dpi PNG, which the generator
places as a single full-page picture.

Why one image rather than a picture with Word text laid over it: the wording
sits against two diagonals, and its position only works if it is measured
against them. Floating text boxes are positioned by the renderer, and Word
and LibreOffice do not agree on that positioning — the same disagreement that
made page numbers unreliable until they were measured and cached. Measuring
the text here, in pixels, against the same geometry that drew the diagonals,
removes the disagreement: both renderers are handed a finished picture.

The trade is that the cover's wording is not selectable text. Every field on
it is repeated on the document control page, which is selectable, so nothing
is lost to search or to copy-and-paste.

Nothing here raises. A missing photograph, a missing logo or a missing font
each degrade to something deliberate, because a cover that fails is a report
that fails.
"""
from __future__ import annotations

import logging
import math
import os
import random
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

# --- page ------------------------------------------------------------------
DPI = 300
MM = DPI / 25.4
W = int(210 * MM)
H = int(297 * MM)
SS = 2                     # supersample factor for drawing

# --- palette ---------------------------------------------------------------
NAVY = (16, 41, 77)
NAVY_DEEP = (11, 30, 58)
NAVY_BAR = (8, 23, 46)
GREEN = (108, 176, 65)
GREEN_LT = (140, 198, 63)
GREEN_DK = (46, 112, 44)
BLUE_WAVE = (58, 140, 196)
WAVE_CYAN = (72, 190, 200)
AIR_BLUE = (86, 158, 224)
AIR_TEAL = (86, 206, 208)
AIR_EMERALD = (96, 206, 128)
TITLE_NAVY = (18, 46, 88)
TITLE_GREEN = (86, 156, 60)
WHITE = (255, 255, 255)
INK = (44, 54, 66)
SUB = (198, 210, 226)
RULE = (52, 78, 118)
STRIP_BG = (244, 246, 248)
STRIP_INK = (92, 102, 114)

# --- geometry, as fractions of the page ------------------------------------
PANEL_TOP_X = 0.660        # where the light panel meets the top edge
PANEL_BOT_X = 0.245        # where it meets the foot of the panel
FACET_A, FACET_B = 0.845, 0.430
STRIPE = 0.0092            # thickness of the green stripe

# --- fonts -----------------------------------------------------------------
# Ordered by preference. The Dockerfile installs fonts best-effort, so none of
# these is guaranteed; the title is auto-fitted, which is what makes falling
# back to a wider face safe rather than merely survivable.
_COND_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/opentype/ibm-plex/IBMPlexSansCondensed-Bold.otf",
    "/usr/share/fonts/truetype/ibm-plex/IBMPlexSansCondensed-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
_COND_REG = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
    "/usr/share/fonts/opentype/ibm-plex/IBMPlexSansCondensed-Regular.otf",
    "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_UI_BOLD = [
    "/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/opentype/ibm-plex/IBMPlexSans-Bold.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
_UI_REG = [
    "/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/opentype/ibm-plex/IBMPlexSans-Regular.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(candidates: List[str], size: int):
    from PIL import ImageFont
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:  # noqa: BLE001
                continue
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# wording helpers
# ---------------------------------------------------------------------------
def date_range(start: Optional[datetime], end: Optional[datetime],
               abbrev: bool = False) -> str:
    """The survey window on one line, collapsing what the two dates share.

    Same month: 6 – 7 July 2026. Same year: 29 June – 2 July 2026. Otherwise
    both dates in full. A single date prints alone rather than as a range.
    """
    def day(d):
        return str(d.day)

    mon = "%b" if abbrev else "%B"

    if not start and not end:
        return "—"
    if not end or (start and start.date() == end.date()):
        d = start or end
        return f"{day(d)} {d.strftime(mon + ' %Y')}"
    if not start:
        return f"{day(end)} {end.strftime(mon + ' %Y')}"
    if start.year == end.year and start.month == end.month:
        return f"{day(start)} – {day(end)} {start.strftime(mon + ' %Y')}"
    if start.year == end.year:
        return (f"{day(start)} {start.strftime(mon)} – "
                f"{day(end)} {end.strftime(mon + ' %Y')}")
    return (f"{day(start)} {start.strftime(mon + ' %Y')} – "
            f"{day(end)} {end.strftime(mon + ' %Y')}")


def _wrap(draw, text: str, font, max_px: float, max_lines: int) -> List[str]:
    """Greedy wrap. A word longer than the line is left to overflow rather
    than hyphenated — a broken company name reads worse than a tight one."""
    words = (text or "").split()
    if not words:
        return ["—"]
    lines, cur = [], words[0]
    for word in words[1:]:
        trial = f"{cur} {word}"
        if draw.textlength(trial, font=font) <= max_px:
            cur = trial
        else:
            lines.append(cur)
            cur = word
            if len(lines) == max_lines:
                break
    if len(lines) < max_lines:
        lines.append(cur)
    return lines[:max_lines]


def _fit_block(draw, text: str, candidates: List[str], start_px: int,
               max_px: float, max_lines: int, floor_px: int
               ) -> Tuple[object, List[str]]:
    """Shrink until the text wraps inside max_lines, then stop.

    Client names run from three characters to sixty. Choosing one size for
    all of them means either the short ones look timid or the long ones spill
    over the diagonal, so the size is chosen per report.
    """
    size = start_px
    while size > floor_px:
        font = _font(candidates, size)
        lines = _wrap(draw, text, font, max_px, max_lines + 1)
        if len(lines) <= max_lines:
            return font, lines[:max_lines]
        size -= 2
    font = _font(candidates, floor_px)
    return font, _wrap(draw, text, font, max_px, max_lines)


def _fit_line(draw, wordings: Sequence[str], fonts: List[str], start_px: int,
              max_px: float, floor_px: int):
    """Pick the first wording that fits, then shrink. Never truncates.

    Used where dropping characters would lose meaning: a monitoring window
    that reads "29 December 2026 – 2 January" has silently lost a year, and
    nobody re-checks a date that looks plausible.
    """
    cands = [c for c in wordings if c] or ["—"]
    for size in range(start_px, floor_px, -2):
        font = _font(fonts, size)
        for cand in cands:
            if draw.textlength(cand, font=font) <= max_px:
                return font, cand
    return _font(fonts, floor_px), cands[-1]


def _track(draw, xy, text: str, font, fill, spacing: float):
    """Letter-spaced small caps. Pillow has no tracking, so it is drawn a
    character at a time."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + spacing
    return x


def _track_w(draw, text: str, font, spacing: float) -> float:
    if not text:
        return 0.0
    return sum(draw.textlength(c, font=font) + spacing for c in text) - spacing


# ---------------------------------------------------------------------------
# the photograph layer
# ---------------------------------------------------------------------------
def _photo_layer(w: int, h: int, photo_path: Optional[str]):
    """The campaign photograph, cover-cropped to the page.

    Cover-cropped, not fitted: the plate is full bleed, so a fitted image
    would leave bars. The crop is biased upward because the subject of these
    photographs — a tripod, a monitoring cabin — sits above centre, and the
    lower third is ground the navy plane covers anyway.
    """
    from PIL import Image, ImageDraw, ImageFilter

    if photo_path and os.path.exists(photo_path):
        try:
            im = Image.open(photo_path).convert("RGB")
            iw, ih = im.size
            target = w / h
            if iw / ih > target:
                nw = int(ih * target)
                im = im.crop(((iw - nw) // 2, 0, (iw + nw) // 2, ih))
            else:
                nh = int(iw / target)
                top = int((ih - nh) * 0.30)
                im = im.crop((0, top, iw, top + nh))
            return im.resize((w, h), Image.LANCZOS)
        except Exception:  # noqa: BLE001
            log.warning("cover photograph unusable — drawing the field "
                        "instead", exc_info=True)

    # No photograph: a plain graduated field. Deliberately plain — an invented
    # scene would be worse than an honest absence on a regulatory document.
    im = Image.new("RGB", (w, h), NAVY)
    d = ImageDraw.Draw(im)
    for i in range(h):
        t = i / h
        d.line([(0, i), (w, i)],
               fill=(int(28 + 44 * t), int(58 + 60 * t), int(96 + 62 * t)))
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx, cy, r = int(w * 0.72), int(h * 0.34), int(w * 0.55)
    gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(70, 96, 132))
    glow = glow.filter(ImageFilter.GaussianBlur(w * 0.10))
    return Image.blend(im, glow, 0.35)


# ---------------------------------------------------------------------------
# icons
# ---------------------------------------------------------------------------
def _icon(d, cx, cy, r, kind, colour=GREEN, ring=True, w_px=2):
    """The small line icons, drawn rather than shipped as files, so the cover
    depends on one asset — the logo — and there is no second set of files to
    lose on a redeploy."""
    lw = max(1, int(w_px))
    if ring:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=colour, width=lw)
    if kind == "cal":
        d.rounded_rectangle([cx - r * .46, cy - r * .40,
                             cx + r * .46, cy + r * .48],
                            radius=int(r * .14), outline=colour, width=lw)
        d.line([(cx - r * .46, cy - r * .14), (cx + r * .46, cy - r * .14)],
               fill=colour, width=lw)
        for sx in (-.24, .24):
            d.line([(cx + r * sx, cy - r * .58), (cx + r * sx, cy - r * .28)],
                   fill=colour, width=lw)
        for ry in (.08, .28):
            for rx in (-.26, 0.0, .26):
                d.rectangle([cx + r * rx - r * .055, cy + r * ry - r * .055,
                             cx + r * rx + r * .055, cy + r * ry + r * .055],
                            fill=colour)
    elif kind == "pin":
        d.ellipse([cx - r * .34, cy - r * .52, cx + r * .34, cy + r * .16],
                  outline=colour, width=lw)
        d.polygon([(cx - r * .17, cy + r * .02), (cx + r * .17, cy + r * .02),
                   (cx, cy + r * .54)], fill=colour)
        d.ellipse([cx - r * .12, cy - r * .30, cx + r * .12, cy - r * .06],
                  fill=colour)
    elif kind == "person":
        d.ellipse([cx - r * .23, cy - r * .46, cx + r * .23, cy - r * .02],
                  outline=colour, width=lw)
        d.arc([cx - r * .50, cy - r * .06, cx + r * .50, cy + r * .80],
              180, 360, fill=colour, width=lw)
    elif kind == "target":
        for f in (.62, .34):
            d.ellipse([cx - r * f, cy - r * f, cx + r * f, cy + r * f],
                      outline=colour, width=lw)
        d.ellipse([cx - r * .11, cy - r * .11, cx + r * .11, cy + r * .11],
                  fill=colour)
    elif kind == "shield":
        d.polygon([(cx, cy - r * .66), (cx + r * .52, cy - r * .40),
                   (cx + r * .43, cy + r * .30), (cx, cy + r * .70),
                   (cx - r * .43, cy + r * .30), (cx - r * .52, cy - r * .40)],
                  outline=colour, width=lw)
        d.line([(cx - r * .22, cy + r * .02), (cx - r * .05, cy + r * .24)],
               fill=colour, width=lw)
        d.line([(cx - r * .05, cy + r * .24), (cx + r * .28, cy - r * .24)],
               fill=colour, width=lw)
    elif kind == "chart":
        for i, hgt in enumerate((.24, .44, .64)):
            bx = cx - r * .48 + i * r * .36
            d.rectangle([bx, cy + r * .40 - r * hgt, bx + r * .20,
                         cy + r * .40], outline=colour, width=lw)
        d.line([(cx - r * .38, cy - r * .20), (cx + r * .46, cy - r * .62)],
               fill=colour, width=lw)
    elif kind == "globe":
        d.ellipse([cx - r * .62, cy - r * .62, cx + r * .62, cy + r * .62],
                  outline=colour, width=lw)
        d.ellipse([cx - r * .28, cy - r * .62, cx + r * .28, cy + r * .62],
                  outline=colour, width=lw)
        d.line([(cx - r * .62, cy), (cx + r * .62, cy)], fill=colour, width=lw)
    elif kind == "leaf":
        d.polygon([(cx - r * .70, cy + r * .46), (cx - r * .12, cy - r * .52),
                   (cx + r * .70, cy - r * .34), (cx + r * .06, cy + r * .50)],
                  fill=colour)
    elif kind == "mail":
        d.rectangle([cx - r * .62, cy - r * .42, cx + r * .62, cy + r * .42],
                    outline=colour, width=lw)
        d.line([(cx - r * .62, cy - r * .42), (cx, cy + r * .06)],
               fill=colour, width=lw)
        d.line([(cx, cy + r * .06), (cx + r * .62, cy - r * .42)],
               fill=colour, width=lw)
    elif kind == "phone":
        d.rounded_rectangle([cx - r * .34, cy - r * .62,
                             cx + r * .34, cy + r * .62],
                            radius=int(r * .20), outline=colour, width=lw)
        d.line([(cx - r * .12, cy + r * .42), (cx + r * .12, cy + r * .42)],
               fill=colour, width=lw)


# ---------------------------------------------------------------------------
# the plate
# ---------------------------------------------------------------------------
def render_cover(out_path: str,
                 *,
                 report_type: Sequence[str] = ("NOISE", "MONITORING",
                                               "REPORT"),
                 eyebrow: str = "ENVIRONMENTAL MONITORING",
                 strapline: Sequence[str] = ("Accurate Monitoring.",
                                             "Reliable Results."),
                 strapline_icons: Optional[Sequence[str]] = None,
                 survey_dates="—",
                 survey_note: Sequence[str] = ("24-hour attended",
                                               "noise survey"),
                 location: str = "—",
                 client: str = "—",
                 report_number: str = "—",
                 revision: str = "00",
                 issue_date: str = "—",
                 revision_label: str = "REVISION",
                 revision_value: Optional[str] = None,
                 third_label: str = "ISSUE DATE",
                 third_lines: Optional[Sequence[str]] = None,
                 company: Sequence[str] = ("Professional People.",
                                           "Reliable Solutions."),
                 green_stripe: bool = True,
                 wave_x0: float = 0.205,
                 wave_rich: bool = False,
                 wave_style: str = "airflow",
                 gas_symbols: Optional[Sequence[str]] = None,
                 navy_left_y: float = 0.495,
                 navy_right_y: float = 1.008,
                 pillars: Optional[Sequence[Tuple[str, str, str, str]]] = None,
                 contacts: Optional[Sequence[Tuple[str, str]]] = None,
                 photo_path: Optional[str] = None,
                 logo_path: Optional[str] = None) -> str:
    """Draw the plate and save it as a 300 dpi PNG.

    ``navy_left_y`` and ``navy_right_y`` describe the navy plane's top edge as
    one line across the page. Where that line drops below the plane's foot the
    plane is a triangle, which is the noise cover; where it stays above, the
    plane spans the full width, which is the air cover. One expression covers
    both, so the two covers cannot drift into different geometry.
    """
    from PIL import Image, ImageDraw

    w, h = W * SS, H * SS

    def X(f):
        return f * w

    def Y(f):
        return f * h

    # --- vertical structure ------------------------------------------------
    # Bands are measured up from the foot of the page, so switching the strip
    # or the contact bar on moves everything above them together instead of
    # needing a second set of coordinates.
    contact_h = 0.045 if contacts else 0.0
    foot_h = 0.094 if (pillars or third_lines) else 0.115
    contact_top = 1.0 - contact_h
    foot_top = contact_top - foot_h
    # The pillar strip is squeezed and the height given to the footer, where
    # the report number, revision and monitoring period live. Those are the
    # only facts on the cover a reader looks up; the pillars are the same
    # four words on every report and can afford to be tight.
    strip_top = foot_top - 0.082 if pillars else foot_top
    base = strip_top                     # foot of the panel and the navy plane

    page = _photo_layer(w, h, photo_path)
    d = ImageDraw.Draw(page, "RGBA")

    def panel_x(yf: float) -> float:
        return PANEL_TOP_X + (PANEL_BOT_X - PANEL_TOP_X) * (yf / base)

    # --- glass facet over the photograph -----------------------------------
    d.polygon([(X(PANEL_TOP_X), 0), (X(FACET_A), 0),
               (X(FACET_B), Y(base)), (X(PANEL_BOT_X), Y(base))],
              fill=(255, 255, 255, 34))

    # --- the light panel ---------------------------------------------------
    d.polygon([(0, 0), (X(PANEL_TOP_X), 0),
               (X(PANEL_BOT_X), Y(base)), (0, Y(base))],
              fill=(255, 255, 255, 250))
    for i in range(int(Y(base))):
        t = i / Y(base)
        d.line([(0, i), (X(panel_x(t * base)), i)],
               fill=(243, 246, 243, int(8 + 60 * t)))

    # --- the navy plane ----------------------------------------------------
    nl, nr = navy_left_y, navy_right_y
    if nr <= base:
        poly = [(0, Y(nl)), (w, Y(nr)), (w, Y(base)), (0, Y(base))]
        edge_end = (w, Y(nr))
    else:
        x_end = (base - nl) / (nr - nl)
        poly = [(0, Y(nl)), (X(x_end), Y(base)), (0, Y(base))]
        edge_end = (X(x_end), Y(base))
    d.polygon(poly, fill=NAVY)
    for i in range(int(Y(nl)), int(Y(base))):
        t = (i - Y(nl)) / max(1.0, Y(base) - Y(nl))
        xr = w if nr <= base else X((i / h - nl) / (nr - nl))
        d.line([(0, i), (xr, i)], fill=(20, 52, 96, int(50 * (1 - t))))
    if green_stripe:
        d.polygon([(0, Y(nl)), edge_end,
                   (edge_end[0], edge_end[1] + Y(STRIPE)),
                   (0, Y(nl + STRIPE))], fill=GREEN)

    # --- the waveform ------------------------------------------------------
    # Decoration, not data. It is identical on every report and must stay that
    # way: a cover that plotted the measured trace would imply the result is
    # on the cover, and at this size the trace is unreadable.
    rnd = random.Random(3)

    def mix(a, b, t):
        t = max(0.0, min(1.0, t))
        return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

    def ramp(t):
        """Blue at the left, cyan through the middle, green at the right."""
        return (mix(BLUE_WAVE, WAVE_CYAN, t / 0.45) if t < 0.45
                else mix(WAVE_CYAN, GREEN_LT, (t - 0.45) / 0.55))

    x0, span = X(wave_x0), X(1.005 - wave_x0)
    if wave_rich:
        # An atmospheric airflow field: translucent ribbons of moving air,
        # particle streams riding them, a hexagonal molecular lattice behind,
        # and the pollutant symbols the report measures, set faintly into the
        # depth. Every layer is drawn twice — once into its own buffer which
        # is blurred and *added* to the page for the volumetric glow, once
        # crisply on top. Light on a dark ground adds; a pale haze painted
        # directly would grey the navy instead of lighting it. The buffer
        # covers only the band, so no full-page image is allocated.
        from PIL import ImageChops, ImageFilter

        band_h = 0.118
        y_front = base - 0.014
        LIGHT_T = 0.60          # where the light falls across the band
        bx0, bx1 = X(wave_x0), X(1.005)
        by0, by1 = Y(y_front - band_h), Y(y_front)
        bw_, bh_ = bx1 - bx0, by1 - by0

        def hue(px, warm=0.0):
            """Blue at the left through to emerald at the right."""
            t = (px - bx0) / max(1.0, bw_)
            c = (mix(AIR_BLUE, AIR_TEAL, t / 0.5) if t < 0.5
                 else mix(AIR_TEAL, AIR_EMERALD, (t - 0.5) / 0.5))
            return mix(c, (255, 255, 255), warm)

        def rgba(c, k, alpha):
            return (int(c[0] * k), int(c[1] * k), int(c[2] * k), int(alpha))

        # Six ribbons at different depths. Each is a band between two curves;
        # thickness swells and narrows along its length, which is what makes
        # it read as a sheet of air turning rather than as a stroke.
        RIBBONS = 6

        def ribbon(idx, t):
            r = idx / (RIBBONS - 1.0)
            depth = 0.30 + 0.70 * r              # 1 = nearest the reader
            cy = (by1 - bh_ * (0.16 + 0.62 * r)
                  - bh_ * 0.30 * math.sin(math.pi * (t ** 0.85) + r * 0.55)
                  - bh_ * 0.10 * math.sin(2 * math.pi * 1.7 * t + r * 2.1))
            half = bh_ * (0.030 + 0.055 * depth) * (
                0.45 + 0.55 * abs(math.sin(math.pi * t * 1.15 + r)))
            return cy, half, depth

        def paint(target, off, dim, crisp):
            # 1. hexagonal molecular lattice, set well back
            hx = bw_ / 26.0
            hy = hx * 0.866
            j = 0
            yy = by0 - hy
            while yy < by1 + hy:
                xx = bx0 + (hx * 0.5 if j % 2 else 0.0)
                while xx < bx1 + hx:
                    pts = [(xx + hx * 0.5 * math.cos(math.radians(60 * q)),
                            yy - off + hx * 0.5 * math.sin(math.radians(60 * q)))
                           for q in range(6)]
                    fade = 0.35 + 0.65 * ((yy - by0) / max(1.0, bh_))
                    target.line(pts + [pts[0]],
                                fill=rgba(hue(xx), dim * 0.30 * fade,
                                          58 * dim * fade),
                                width=max(1, int(w * (0.0009 if crisp
                                                      else 0.0016))))
                    xx += hx * 1.5
                yy += hy
                j += 1

            # 2. fine mesh streamlines drifting through the field
            for k in range(16):
                f = k / 15.0
                prev = None
                t = 0.0
                while t <= 1.0:
                    px = bx0 + t * bw_
                    py = (by1 - bh_ * (0.10 + 0.80 * f)
                          - bh_ * 0.16 * math.sin(math.pi * t + f * 1.6))
                    if prev:
                        target.line([prev, (px, py - off)],
                                    fill=rgba(hue(px), dim * 0.45,
                                              70 * dim),
                                    width=max(1, int(w * (0.0006 if crisp
                                                          else 0.0013))))
                    prev = (px, py - off)
                    t += 0.02

            # 3. the ribbons themselves — translucent sheets, bright at the
            #    edges where a glass surface catches the light
            for idx in range(RIBBONS):
                t = 0.0
                while t <= 1.0:
                    px = bx0 + t * bw_
                    cy, half, depth = ribbon(idx, t)
                    fade = math.sin(math.pi * min(1.0, t * 1.04)) ** 0.5
                    c = hue(px)
                    target.line([(px, cy - half - off), (px, cy + half - off)],
                                fill=rgba(c, dim * (0.30 + 0.35 * depth),
                                          (58 if crisp else 92) * dim * fade),
                                width=max(1, int(bw_ * 0.0016)))
                    for edge in (-half, half):
                        ec = mix(c, (255, 255, 255), 0.55 if crisp else 0.25)
                        rr = w * (0.00050 if crisp else 0.0016) * (
                            0.6 + 0.6 * depth)
                        target.ellipse([px - rr, cy + edge - off - rr,
                                        px + rr, cy + edge - off + rr],
                                       fill=rgba(ec, dim, 215 * dim * fade))
                    # Specular highlight. The light sits off to the upper
                    # right, so the sheen runs where the ribbon turns to face
                    # it and dies away either side; a highlight spread evenly
                    # along the edge would read as a white stroke, not shine.
                    spec = (math.exp(-((t - LIGHT_T) ** 2) / 0.022)
                            * (0.30 + 0.55 * depth) * fade * 0.55)
                    if spec > 0.02:
                        hc = mix(c, (255, 255, 255), 0.78)
                        hr = w * (0.00068 if crisp else 0.0020) * (
                            0.5 + 0.9 * spec)
                        target.ellipse(
                            [px - hr, cy - half - off - hr,
                             px + hr, cy - half - off + hr],
                            fill=rgba(hc, dim, 235 * dim * spec))
                        hr2 = hr * 0.45
                        target.ellipse(
                            [px - hr2, cy + half - off - hr2,
                             px + hr2, cy + half - off + hr2],
                            fill=rgba(hc, dim, 120 * dim * spec))
                    t += 0.0022

            # 4. particle streams riding the ribbons
            pr = random.Random(11)
            for _ in range(1500):
                idx = pr.randrange(RIBBONS)
                t = pr.random()
                cy, half, depth = ribbon(idx, t)
                px = bx0 + t * bw_
                py = cy + pr.uniform(-1.35, 1.35) * half
                fade = math.sin(math.pi * min(1.0, t * 1.04)) ** 0.6
                spec = math.exp(-((t - LIGHT_T) ** 2) / 0.045) * 0.55
                c = mix(hue(px), (255, 255, 255),
                        (0.45 if crisp else 0.15) + 0.28 * spec)
                rr = (w * (0.00055 if crisp else 0.0017)
                      * (0.5 + 0.7 * depth) * (1.0 + 0.30 * spec))
                target.ellipse([px - rr, py - off - rr, px + rr, py - off + rr],
                               fill=rgba(c, dim, (235 + 20 * spec) * dim * fade))

        def light_sweep(target, off, dim):
            """A soft sheet of light raked across the field. It exists only in
            the blurred pass — at full resolution it would be a grey wedge;
            blurred and added it is the wash the ribbons are lit by."""
            steps = 46
            for q in range(steps):
                f = q / (steps - 1.0)
                bright = math.sin(math.pi * f) ** 1.6
                cxp = bx0 + (LIGHT_T - 0.22 + 0.44 * f) * bw_
                target.line([(cxp, by0 - off - bh_ * 0.35),
                             (cxp - bw_ * 0.10, by1 - off + bh_ * 0.20)],
                            fill=(int(190 * bright * dim),
                                  int(215 * bright * dim),
                                  int(230 * bright * dim),
                                  int(120 * bright * dim)),
                            width=max(1, int(bw_ * 0.012)))

        y_top = max(0, int(by0 - h * 0.070))
        y_bot = min(h, int(by1 + h * 0.028))
        glow = Image.new("RGB", (w, y_bot - y_top), (0, 0, 0))
        gd = ImageDraw.Draw(glow, "RGBA")
        light_sweep(gd, y_top, 0.24)
        paint(gd, y_top, 0.55, False)
        bloom = ImageChops.add(
            glow.filter(ImageFilter.GaussianBlur(w * 0.0080)),
            glow.filter(ImageFilter.GaussianBlur(w * 0.0020)), scale=1.0)
        strip = page.crop((0, y_top, w, y_bot)).convert("RGB")
        page.paste(ImageChops.add(strip, bloom), (0, y_top))
        d = ImageDraw.Draw(page, "RGBA")
        paint(d, 0, 1.0, True)

        # 5. the measured species, set faintly into the field. Deliberately
        #    low-contrast and placed only in the open right-hand half: they
        #    name what the report measures, and must not read as a legend or
        #    invite anyone to look for values beside them.
        if gas_symbols:
            gf = _font(_UI_REG, int(h * 0.0132))
            spots = [(0.36, 0.30), (0.53, 0.66), (0.66, 0.20),
                     (0.78, 0.54), (0.90, 0.34)]
            for (sx, sy), sym in zip(spots, gas_symbols):
                px = bx0 + sx * bw_
                py = by1 - (0.14 + 0.72 * sy) * bh_
                tw = d.textlength(sym, font=gf)
                rr = max(tw * 0.82, w * 0.010)
                pts = [(px + rr * math.cos(math.radians(60 * q + 30)),
                        py + rr * math.sin(math.radians(60 * q + 30)))
                       for q in range(6)]
                d.line(pts + [pts[0]], fill=hue(px, 0.30) + (54,),
                       width=max(1, int(w * 0.0009)))
                d.text((px - tw / 2, py - h * 0.0072), sym, font=gf,
                       fill=hue(px, 0.55) + (150,))
    else:
        for k in range(11):
            yb = Y(base - 0.073) + k * Y(0.0088)
            amp = Y(0.0165) * (0.75 + 0.45 * rnd.random())
            phase = k * 0.42 + rnd.uniform(-0.12, 0.12)
            t = 0.0
            while t <= 1.0:
                px = x0 + t * span
                env = math.sin(math.pi * min(1.0, t * 1.06)) ** 0.85
                py = yb - math.sin(t * 7.2 + phase) * amp * env - env * Y(0.026)
                rr = w * 0.00105
                d.ellipse([px - rr, py - rr, px + rr, py + rr],
                          fill=mix(BLUE_WAVE, GREEN_LT, (t - 0.10) / 0.75)
                          + (int(225 * env),))
                t += 0.0030

    # Vertical texture under the ribbons. In the rich field it hangs from a
    # smooth curve rather than from a flat line, so it reads as part of the
    # flow instead of as a rectangular patch of dots.
    stem_x0, stem_x1 = (0.400, 0.930) if wave_rich else (0.320, 0.980)
    t = 0.0
    while t <= 1.0:
        px = X(stem_x0) + t * X(stem_x1 - stem_x0)
        env = math.sin(math.pi * t) ** 0.75
        if wave_rich:
            top = (Y(base - 0.052)
                   - math.sin(t * 2.4 + 0.6) * Y(0.016) * env
                   - env * Y(0.012))
            bot = Y(base - 0.024)
            alpha = int(105 * env)
        else:
            top = Y(base - 0.0175) - env * Y(0.055) * (
                0.30 + 0.70 * abs(math.sin(t * 21.0)))
            bot = Y(base - 0.0175)
            alpha = int(140 * env)
        col = ramp(t) if wave_rich else mix(BLUE_WAVE, GREEN_LT, t * 1.10)
        yy = bot
        while yy > top:
            rr = w * 0.00095
            d.ellipse([px - rr, yy - rr, px + rr, yy + rr],
                      fill=col + (alpha,))
            yy -= Y(0.0042)
        t += 0.0052

    # --- bands -------------------------------------------------------------
    if pillars:
        d.rectangle([0, Y(strip_top), w, Y(foot_top)], fill=STRIP_BG)
    d.rectangle([0, Y(foot_top), w, Y(contact_top)], fill=NAVY_DEEP)
    if contacts:
        d.rectangle([0, Y(contact_top), w, h], fill=NAVY_BAR)
        d.rectangle([0, Y(contact_top), w, Y(contact_top) + h * 0.0012],
                    fill=(38, 62, 96))

    # --- logo --------------------------------------------------------------
    # Supplied on a white background rather than with an alpha channel, so the
    # white is keyed out by minimum channel. That keeps the drop shadow
    # feathering and stops a white box showing against the panel tint.
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGB")
            try:
                import numpy as np
                arr = np.asarray(logo).astype(np.int16)
                alpha = np.clip((255 - arr.min(axis=2)) * 1.30, 0,
                                255).astype("uint8")
                mask = Image.fromarray(alpha, mode="L")
            except Exception:  # noqa: BLE001
                mask = logo.convert("L").point(
                    lambda v: min(255, int((255 - v) * 1.30)))
            logo = logo.convert("RGBA")
            logo.putalpha(mask)
            lw = int(X(0.245))
            logo = logo.resize((lw, max(1, int(lw * logo.height / logo.width))),
                               Image.LANCZOS)
            page.paste(logo, (int(X(0.048)), int(Y(0.030))), logo)
            d = ImageDraw.Draw(page, "RGBA")
        except Exception:  # noqa: BLE001
            log.warning("cover logo unusable — omitted", exc_info=True)

    # --- eyebrow -----------------------------------------------------------
    _track(d, (X(0.055), Y(0.176)), eyebrow, _font(_COND_REG, int(h * 0.0145)),
           TITLE_NAVY, w * 0.0027)
    d.rectangle([X(0.055), Y(0.2055), X(0.126), Y(0.2078)], fill=GREEN)

    # --- title -------------------------------------------------------------
    # Sized against the diagonal rather than set by hand. The panel narrows as
    # it descends, so the longest line is measured where its baseline falls;
    # a longer report type shrinks to fit instead of running into the photo.
    top, tx = 0.232, 0.052
    longest = max(report_type, key=len)
    size = int(h * 0.0605)
    while size > int(h * 0.030):
        font = _font(_COND_BOLD, size)
        bottom = top + (size * 1.075 + size * 0.78) / h
        if (X(tx) + d.textlength(longest, font=font)
                <= X(panel_x(bottom) - 0.022)):
            break
        size -= 2
    font = _font(_COND_BOLD, size)
    lead = size * 1.075 / h
    palette = (TITLE_NAVY, TITLE_GREEN, TITLE_NAVY, TITLE_NAVY)
    for i, line in enumerate(report_type):
        d.text((X(tx), Y(top + i * lead)), line, font=font,
               fill=palette[i % len(palette)])

    # --- strapline ---------------------------------------------------------
    sl_top = top + len(report_type) * lead + 0.019
    sl_lead = 0.0315
    d.rectangle([X(0.055), Y(sl_top + 0.001), X(0.0585),
                 Y(sl_top + sl_lead * (len(strapline) - 1) + 0.026)],
                fill=GREEN)
    sf = _font(_UI_REG, int(h * 0.0180))
    for i, line in enumerate(strapline):
        ly = sl_top + i * sl_lead
        tx_line = 0.075
        if strapline_icons and i < len(strapline_icons):
            _icon(d, X(0.090), Y(ly + 0.0110), w * 0.0128,
                  strapline_icons[i], GREEN, ring=True, w_px=int(w * 0.0013))
            tx_line = 0.113
        last = strapline_icons and i == len(strapline) - 1
        d.text((X(tx_line), Y(ly)), line, font=sf,
               fill=TITLE_GREEN if last else INK)

    # --- detail rows -------------------------------------------------------
    def room(yf: float) -> float:
        """Width available inside the navy plane at a given height."""
        edge = 1.0 if nr <= base else min(1.0, max(0.0, (yf - nl) / (nr - nl)))
        return X(edge) - X(0.108) - X(0.022)

    # The row block is anchored to the foot of the navy plane, not to its
    # top edge. Its spacing is fixed, and the last row carries two lines, so
    # anchoring downward keeps the rows clear of whatever band sits below —
    # the footer on the noise cover, the value strip on the air one —
    # whichever of the two layouts is being drawn.
    row_gap = 0.0755
    rows_top = base - 0.064 - 2 * row_gap
    cx, tx2 = X(0.078), X(0.108)
    lab_f = _font(_UI_BOLD, int(h * 0.0136))
    sub_f = _font(_UI_REG, int(h * 0.0142))
    val_px = int(h * 0.0152)
    rule_w = max(1, int(w * 0.0013))

    y0 = rows_top
    _icon(d, cx, Y(y0 + 0.0150), w * 0.026, "cal", GREEN, w_px=int(w * 0.0017))
    df, dtext = _fit_line(
        d, survey_dates if isinstance(survey_dates, (list, tuple))
        else [survey_dates], _UI_BOLD, val_px, room(y0 + 0.015),
        int(h * 0.0104))
    d.text((tx2, Y(y0)), dtext, font=df, fill=WHITE)
    for i, line in enumerate(survey_note):
        d.text((tx2, Y(y0 + 0.0200 + i * 0.0170)), line, font=sub_f, fill=SUB)
    d.line([(X(0.040), Y(y0 + row_gap - 0.018)),
            (X(0.290), Y(y0 + row_gap - 0.018))], fill=RULE, width=rule_w)

    y1 = rows_top + row_gap
    _icon(d, cx, Y(y1 + 0.0155), w * 0.026, "pin", GREEN, w_px=int(w * 0.0017))
    _track(d, (tx2, Y(y1 - 0.010)), "MONITORING LOCATION", lab_f, GREEN_LT,
           w * 0.0011)
    lf, llines = _fit_block(d, (location or "—").upper(), _UI_BOLD, val_px,
                            min(room(y1 + 0.02), X(0.215)), 2,
                            int(h * 0.0108))
    for i, line in enumerate(llines):
        d.text((tx2, Y(y1 + 0.0075 + i * 0.0190)), line, font=lf, fill=WHITE)
    d.line([(X(0.040), Y(y1 + row_gap - 0.018)),
            (X(0.290), Y(y1 + row_gap - 0.018))], fill=RULE, width=rule_w)

    y2 = rows_top + 2 * row_gap
    _icon(d, cx, Y(y2 + 0.0155), w * 0.026, "person", GREEN,
          w_px=int(w * 0.0017))
    _track(d, (tx2, Y(y2 - 0.010)), "CLIENT", lab_f, GREEN_LT, w * 0.0011)
    cf, clines = _fit_block(d, client or "—", _UI_BOLD, val_px,
                            min(room(y2 + 0.02), X(0.215)), 2,
                            int(h * 0.0108))
    for i, line in enumerate(clines):
        d.text((tx2, Y(y2 + 0.0075 + i * 0.0190)), line, font=cf, fill=WHITE)

    # --- value pillars -----------------------------------------------------
    if pillars:
        n = len(pillars)
        band = 1.0 / n
        t_f = _font(_UI_BOLD, int(h * 0.0116))
        b_f = _font(_UI_REG, int(h * 0.0096))
        mid = (strip_top + foot_top) / 2
        for i, (kind, title, l1, l2) in enumerate(pillars):
            ccx = X(band * (i + 0.5))
            _icon(d, ccx, Y(mid - 0.0205), w * 0.0175, kind, GREEN_DK,
                  ring=False, w_px=int(w * 0.0016))
            tw = _track_w(d, title, t_f, w * 0.0012)
            _track(d, (ccx - tw / 2, Y(mid - 0.0015)), title, t_f, GREEN_DK,
                   w * 0.0012)
            for j, line in enumerate((l1, l2)):
                lw2 = d.textlength(line, font=b_f)
                d.text((ccx - lw2 / 2, Y(mid + 0.0140 + j * 0.0125)), line,
                       font=b_f, fill=STRIP_INK)
            if i:
                d.line([(X(band * i), Y(strip_top + 0.013)),
                        (X(band * i), Y(foot_top - 0.013))],
                       fill=(214, 220, 226), width=max(1, int(w * 0.0010)))

    # --- footer wording ----------------------------------------------------
    # Laid out from measured widths. At fixed positions "REPORT NUMBER" ran
    # under "REVISION" as soon as a longer issue date widened the block, and
    # the rules landed through the labels.
    third = list(third_lines) if third_lines else [issue_date or "—"]
    fields = [("REPORT NUMBER", (report_number or "—",)),
              (revision_label, (revision_value or f"Rev {revision or '00'}",)),
              (third_label, tuple(third))]
    lab_sp = w * 0.0016
    gap = X(0.024)
    lab_sz, val_sz = int(h * 0.0124), int(h * 0.0200)
    lab_y = foot_top + 0.0180
    val_y = foot_top + 0.0435
    while True:
        flab = _font(_UI_BOLD, lab_sz)
        fval = _font(_UI_BOLD, val_sz)
        widths = [max(_track_w(d, lab, flab, lab_sp),
                      max(d.textlength(v, font=fval) for v in vals))
                  for lab, vals in fields]
        if (X(0.050) + sum(widths) + gap * len(fields) <= X(0.560)
                or lab_sz <= int(h * 0.0076)):
            break
        lab_sz -= 1
        val_sz -= 2
    x = X(0.050)
    for (lab, vals), cw in zip(fields, widths):
        _track(d, (x, Y(lab_y)), lab, flab, (128, 190, 112), lab_sp)
        for j, v in enumerate(vals):
            d.text((x, Y(val_y + j * 0.0195)), v, font=fval, fill=WHITE)
        x += cw + gap
        d.line([(x - gap / 2, Y(foot_top + 0.012)),
                (x - gap / 2, Y(contact_top - 0.012))],
               fill=(50, 74, 112), width=max(1, int(w * 0.0011)))

    _icon(d, X(0.592), Y(lab_y + 0.0150), w * 0.015, "leaf", GREEN, ring=False)
    gx = cur = X(0.628)
    for txt, fnt, col in [("For a ", _font(_UI_REG, int(h * 0.0158)), WHITE),
                          ("Sustainable", _font(_UI_BOLD, int(h * 0.0158)),
                           GREEN_LT),
                          (" Tomorrow", _font(_UI_REG, int(h * 0.0158)),
                           WHITE)]:
        d.text((cur, Y(lab_y - 0.004)), txt, font=fnt, fill=col)
        cur += d.textlength(txt, font=fnt)
    # Pinned to the bottom of the footer band rather than to the labels
    # above, because the band is shorter when a contact bar sits under it and
    # the second line was running into the bar.
    small = _font(_UI_REG, int(h * 0.0148))
    comp_top = contact_top - 0.0180 * len(company) - 0.005
    for j, line in enumerate(company):
        d.text((gx, Y(comp_top + j * 0.0180)), line, font=small, fill=SUB)

    # --- contact bar -------------------------------------------------------
    if contacts:
        cy_ = (contact_top + 1.0) / 2
        c_f = _font(_UI_REG, int(h * 0.0135))
        span = 0.90 / len(contacts)
        for i, (kind, text) in enumerate(contacts):
            bx = X(0.050 + span * i)
            _icon(d, bx + w * 0.010, Y(cy_), w * 0.0115, kind, GREEN_LT,
                  ring=False, w_px=int(w * 0.0013))
            d.text((bx + w * 0.030, Y(cy_ - 0.0082)), text, font=c_f,
                   fill=(214, 224, 236))

    page.resize((W, H), Image.LANCZOS).save(out_path, "PNG", dpi=(DPI, DPI))
    return out_path


# ---------------------------------------------------------------------------
# placing the plate in a document
# ---------------------------------------------------------------------------
def bleed_first_picture(docx_path: str) -> bool:
    """Turn the document's first inline picture into a page-anchored one.

    An inline picture at full page height is laid out inside a line box, and
    the line box aligns it to the baseline: the top is clipped and white is
    left at the foot. Forcing the leading to the page depth does not fix it,
    it only moves where the clipping happens. Anchoring the picture to the
    page, behind the text, takes it out of the line box altogether, which is
    how a full-bleed cover is meant to be built and how Word and LibreOffice
    come to place it identically.

    Run after the template is rendered and saved: docxtpl inserts the picture
    inline, and there is nothing to convert until it has.
    """
    try:
        from docx import Document
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        doc = Document(docx_path)
        inline = None
        for p in doc.paragraphs:
            found = p._p.find(".//" + qn("w:drawing") + "/" + qn("wp:inline"))
            if found is not None:
                inline = found
                break
        if inline is None:
            return False

        anchor = OxmlElement("wp:anchor")
        for k, v in (("distT", "0"), ("distB", "0"), ("distL", "0"),
                     ("distR", "0"), ("simplePos", "0"),
                     ("relativeHeight", "1"), ("behindDoc", "1"),
                     ("locked", "0"), ("layoutInCell", "1"),
                     ("allowOverlap", "1")):
            anchor.set(k, v)
        sp = OxmlElement("wp:simplePos")
        sp.set("x", "0")
        sp.set("y", "0")
        anchor.append(sp)
        for tag in ("wp:positionH", "wp:positionV"):
            pos = OxmlElement(tag)
            pos.set("relativeFrom", "page")
            off = OxmlElement("wp:posOffset")
            off.text = "0"
            pos.append(off)
            anchor.append(pos)
        for child in list(inline):
            name = child.tag.split("}")[-1]
            if name == "extent":
                anchor.append(child)
                eff = OxmlElement("wp:effectExtent")
                for e in ("l", "t", "r", "b"):
                    eff.set(e, "0")
                anchor.append(eff)
                anchor.append(OxmlElement("wp:wrapNone"))
            elif name != "effectExtent":
                anchor.append(child)
        drawing = inline.getparent()
        drawing.remove(inline)
        drawing.append(anchor)
        doc.save(docx_path)
        return True
    except Exception:  # noqa: BLE001
        log.warning("cover plate could not be anchored to the page — it will "
                    "render inline", exc_info=True)
        return False
