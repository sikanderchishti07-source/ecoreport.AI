# -*- coding: utf-8 -*-
"""Render the noise report cover as a single full-bleed A4 plate.

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
it — client, report number, revision, issue date, monitoring location — is
repeated on the document control page, which is selectable, so nothing is
lost to search or to copy-and-paste.

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
from typing import List, Optional, Tuple

log = logging.getLogger(__name__)

# --- page ------------------------------------------------------------------
DPI = 300
MM = DPI / 25.4
W = int(210 * MM)          # 2480
H = int(297 * MM)          # 3508
SS = 2                     # supersample factor for drawing

# --- palette ---------------------------------------------------------------
NAVY = (16, 41, 77)
NAVY_DEEP = (11, 30, 58)
GREEN = (108, 176, 65)
GREEN_LT = (140, 198, 63)
BLUE_WAVE = (58, 140, 196)
TITLE_NAVY = (18, 46, 88)
TITLE_GREEN = (86, 156, 60)
WHITE = (255, 255, 255)
INK = (44, 54, 66)
SUB = (198, 210, 226)
RULE = (52, 78, 118)

# --- geometry, as fractions of the page ------------------------------------
PANEL_TOP_X = 0.660        # where the light panel meets the top edge
PANEL_BOT_X = 0.245        # where it meets the footer
FACET_A, FACET_B = 0.845, 0.430    # the translucent glass facet
NAVY_LEFT_Y = 0.495        # navy plane at the left edge
NAVY_FOOT_X = 0.760        # navy plane where it meets the footer
FOOT_Y = 0.885             # top of the footer band
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
def date_range(start: Optional[datetime], end: Optional[datetime]) -> str:
    """The survey window on one line, collapsing what the two dates share.

    Same month: 6 – 7 July 2026. Same year: 29 June – 2 July 2026. Otherwise
    both dates in full. A single date prints alone rather than as a range.
    """
    def day(d):
        return str(d.day)

    if not start and not end:
        return "—"
    if not end or (start and start.date() == end.date()):
        d = start or end
        return f"{day(d)} {d.strftime('%B %Y')}"
    if not start:
        return f"{day(end)} {end.strftime('%B %Y')}"
    if start.year == end.year and start.month == end.month:
        return f"{day(start)} – {day(end)} {start.strftime('%B %Y')}"
    if start.year == end.year:
        return (f"{day(start)} {start.strftime('%B')} – "
                f"{day(end)} {end.strftime('%B %Y')}")
    return (f"{day(start)} {start.strftime('%B %Y')} – "
            f"{day(end)} {end.strftime('%B %Y')}")


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


def _track(draw, xy, text: str, font, fill, spacing: float):
    """Letter-spaced small caps. Pillow has no tracking, so it is drawn a
    character at a time."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + spacing
    return x


# ---------------------------------------------------------------------------
# the photograph layer
# ---------------------------------------------------------------------------
def _photo_layer(w: int, h: int, photo_path: Optional[str]):
    """The campaign photograph, cover-cropped to the page.

    Cover-cropped, not fitted: the plate is full bleed, so a fitted image
    would leave bars. The crop is biased upward because the subject of a
    tripod photograph sits above centre and the lower third is ground that
    the navy plane covers anyway.
    """
    from PIL import Image, ImageDraw, ImageFilter

    if photo_path and os.path.exists(photo_path):
        try:
            im = Image.open(photo_path).convert("RGB")
            iw, ih = im.size
            target = w / h
            if iw / ih > target:                     # too wide, crop sides
                nw = int(ih * target)
                im = im.crop(((iw - nw) // 2, 0, (iw + nw) // 2, ih))
            else:                                    # too tall, crop bottom
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
# the plate
# ---------------------------------------------------------------------------
def render_cover(out_path: str,
                 *,
                 report_type: Tuple[str, str, str] = ("NOISE", "MONITORING",
                                                      "REPORT"),
                 eyebrow: str = "ENVIRONMENTAL MONITORING",
                 strapline: Tuple[str, str] = ("Accurate Monitoring.",
                                               "Reliable Results."),
                 survey_dates: str = "—",
                 survey_note: Tuple[str, str] = ("24-hour attended",
                                                 "noise survey"),
                 location: str = "—",
                 client: str = "—",
                 report_number: str = "—",
                 revision: str = "00",
                 issue_date: str = "—",
                 company: Tuple[str, str] = ("Professional People.",
                                             "Reliable Solutions."),
                 photo_path: Optional[str] = None,
                 logo_path: Optional[str] = None) -> str:
    from PIL import Image, ImageDraw

    w, h = W * SS, H * SS

    def X(f):
        return f * w

    def Y(f):
        return f * h

    page = _photo_layer(w, h, photo_path)
    d = ImageDraw.Draw(page, "RGBA")

    # -- glass facet over the photograph, right of the panel ---------------
    d.polygon([(X(PANEL_TOP_X), 0), (X(FACET_A), 0),
               (X(FACET_B), Y(FOOT_Y)), (X(PANEL_BOT_X), Y(FOOT_Y))],
              fill=(255, 255, 255, 34))

    # -- the light panel ---------------------------------------------------
    def panel_x(yf: float) -> float:
        """Right edge of the light panel at a given height."""
        return PANEL_TOP_X + (PANEL_BOT_X - PANEL_TOP_X) * (yf / FOOT_Y)

    d.polygon([(0, 0), (X(PANEL_TOP_X), 0),
               (X(PANEL_BOT_X), Y(FOOT_Y)), (0, Y(FOOT_Y))],
              fill=(255, 255, 255, 250))
    for i in range(int(Y(FOOT_Y))):                  # faint downward tint
        t = i / Y(FOOT_Y)
        d.line([(0, i), (X(panel_x(t * FOOT_Y)), i)],
               fill=(243, 246, 243, int(8 + 60 * t)))

    # -- the navy plane and the stripe that rides its edge -----------------
    d.polygon([(0, Y(NAVY_LEFT_Y)), (X(NAVY_FOOT_X), Y(FOOT_Y)),
               (0, Y(FOOT_Y))], fill=NAVY)
    for i in range(int(Y(NAVY_LEFT_Y)), int(Y(FOOT_Y))):
        t = (i - Y(NAVY_LEFT_Y)) / (Y(FOOT_Y) - Y(NAVY_LEFT_Y))
        d.line([(0, i), (X(NAVY_FOOT_X) * t, i)],
               fill=(20, 52, 96, int(50 * (1 - t))))
    d.polygon([(0, Y(NAVY_LEFT_Y)), (X(NAVY_FOOT_X), Y(FOOT_Y)),
               (X(NAVY_FOOT_X), Y(FOOT_Y + STRIPE)),
               (0, Y(NAVY_LEFT_Y + STRIPE))], fill=GREEN)

    # -- the waveform ------------------------------------------------------
    # Decoration, not data. It is identical on every report and must stay
    # that way: a cover that plotted the measured trace would imply the
    # result is on the cover, and at this size the trace is unreadable.
    rnd = random.Random(3)

    def mix(a, b, t):
        t = max(0.0, min(1.0, t))
        return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

    for k in range(11):
        base = Y(0.812) + k * Y(0.0088)
        amp = Y(0.0165) * (0.75 + 0.45 * rnd.random())
        phase = k * 0.42 + rnd.uniform(-0.12, 0.12)
        t = 0.0
        while t <= 1.0:
            px = X(0.205) + t * X(0.800)
            env = math.sin(math.pi * min(1.0, t * 1.06)) ** 0.85
            py = base - math.sin(t * 7.2 + phase) * amp * env - env * Y(0.026)
            rr = w * 0.00105
            d.ellipse([px - rr, py - rr, px + rr, py + rr],
                      fill=mix(BLUE_WAVE, GREEN_LT, (t - 0.10) / 0.75)
                      + (int(225 * env),))
            t += 0.0030
    t = 0.0
    while t <= 1.0:                                   # vertical stems
        px = X(0.320) + t * X(0.660)
        env = math.sin(math.pi * t) ** 0.75
        hgt = env * Y(0.055) * (0.30 + 0.70 * abs(math.sin(t * 21.0)))
        col = mix(BLUE_WAVE, GREEN_LT, t * 1.10)
        yy = Y(0.902)
        while yy > Y(0.902) - hgt:
            rr = w * 0.00095
            d.ellipse([px - rr, yy - rr, px + rr, yy + rr],
                      fill=col + (int(140 * env),))
            yy -= Y(0.0042)
        t += 0.0052

    # -- footer band -------------------------------------------------------
    d.rectangle([0, Y(FOOT_Y), w, h], fill=NAVY_DEEP)

    # -- logo --------------------------------------------------------------
    # Supplied on a white background rather than with an alpha channel, so
    # the white is keyed out by minimum channel. That keeps the drop shadow
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

    # -- eyebrow -----------------------------------------------------------
    _track(d, (X(0.055), Y(0.176)), eyebrow, _font(_COND_REG, int(h * 0.0145)),
           TITLE_NAVY, w * 0.0027)
    d.rectangle([X(0.055), Y(0.2055), X(0.126), Y(0.2078)], fill=GREEN)

    # -- title -------------------------------------------------------------
    # Sized against the diagonal rather than set by hand. The panel narrows
    # as it descends, so the longest line is measured where its baseline
    # falls; an Arabic edition or a longer report type shrinks to fit instead
    # of running into the photograph.
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
    for i, (line, colour) in enumerate(zip(
            report_type, (TITLE_NAVY, TITLE_GREEN, TITLE_NAVY))):
        d.text((X(tx), Y(top + i * lead)), line, font=font, fill=colour)

    # -- strapline ---------------------------------------------------------
    d.rectangle([X(0.055), Y(0.441), X(0.0585), Y(0.502)], fill=GREEN)
    sf = _font(_UI_REG, int(h * 0.0180))
    d.text((X(0.075), Y(0.4425)), strapline[0], font=sf, fill=INK)
    d.text((X(0.075), Y(0.4735)), strapline[1], font=sf, fill=INK)

    # -- detail rows -------------------------------------------------------
    def icon(cx, cy, r, kind):
        lw_ = max(1, int(w * 0.0017))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=GREEN, width=lw_)
        if kind == "cal":
            d.rounded_rectangle([cx - r * .46, cy - r * .40,
                                 cx + r * .46, cy + r * .48],
                                radius=int(r * .14), outline=GREEN, width=lw_)
            d.line([(cx - r * .46, cy - r * .14), (cx + r * .46, cy - r * .14)],
                   fill=GREEN, width=lw_)
            for sx in (-.24, .24):
                d.line([(cx + r * sx, cy - r * .58), (cx + r * sx, cy - r * .28)],
                       fill=GREEN, width=lw_)
            for ry in (.08, .28):
                for rx in (-.26, 0.0, .26):
                    d.rectangle([cx + r * rx - r * .055, cy + r * ry - r * .055,
                                 cx + r * rx + r * .055, cy + r * ry + r * .055],
                                fill=GREEN)
        elif kind == "pin":
            d.ellipse([cx - r * .34, cy - r * .52, cx + r * .34, cy + r * .16],
                      outline=GREEN, width=lw_)
            d.polygon([(cx - r * .17, cy + r * .02), (cx + r * .17, cy + r * .02),
                       (cx, cy + r * .54)], fill=GREEN)
            d.ellipse([cx - r * .12, cy - r * .30, cx + r * .12, cy - r * .06],
                      fill=GREEN)
        else:
            d.ellipse([cx - r * .23, cy - r * .46, cx + r * .23, cy - r * .02],
                      outline=GREEN, width=lw_)
            d.arc([cx - r * .50, cy - r * .06, cx + r * .50, cy + r * .80],
                  180, 360, fill=GREEN, width=lw_)

    cx, tx2 = X(0.078), X(0.108)
    lab_f = _font(_UI_BOLD, int(h * 0.0136))
    sub_f = _font(_UI_REG, int(h * 0.0142))
    # Rows sit inside the navy plane, which widens as it descends, so each
    # row's own width limit is taken from the edge at its own height.
    def room(yf: float) -> float:
        return X(NAVY_FOOT_X * (yf - NAVY_LEFT_Y)
                 / (FOOT_Y - NAVY_LEFT_Y)) - tx2 - X(0.030)

    icon(cx, Y(0.6635), w * 0.026, "cal")
    d.text((tx2, Y(0.6485)), survey_dates, font=_font(_UI_BOLD, int(h * 0.0152)),
           fill=WHITE)
    d.text((tx2, Y(0.6685)), survey_note[0], font=sub_f, fill=SUB)
    d.text((tx2, Y(0.6855)), survey_note[1], font=sub_f, fill=SUB)
    d.line([(X(0.040), Y(0.7060)), (X(0.290), Y(0.7060))], fill=RULE,
           width=max(1, int(w * 0.0013)))

    icon(cx, Y(0.7460), w * 0.026, "pin")
    _track(d, (tx2, Y(0.7200)), "MONITORING LOCATION", lab_f, GREEN_LT,
           w * 0.0011)
    lf, llines = _fit_block(d, (location or "—").upper(), _UI_BOLD,
                            int(h * 0.0152), min(room(0.760), X(0.215)), 2, int(h * 0.0108))
    for i, line in enumerate(llines):
        d.text((tx2, Y(0.7375 + i * 0.0190)), line, font=lf, fill=WHITE)
    d.line([(X(0.040), Y(0.7805)), (X(0.290), Y(0.7805))], fill=RULE,
           width=max(1, int(w * 0.0013)))

    icon(cx, Y(0.8200), w * 0.026, "person")
    _track(d, (tx2, Y(0.7940)), "CLIENT", lab_f, GREEN_LT, w * 0.0011)
    cf, clines = _fit_block(d, client or "—", _UI_BOLD, int(h * 0.0152),
                            min(room(0.834), X(0.215)), 2, int(h * 0.0108))
    for i, line in enumerate(clines):
        d.text((tx2, Y(0.8115 + i * 0.0190)), line, font=cf, fill=WHITE)

    # -- footer wording ----------------------------------------------------
    flab = _font(_UI_BOLD, int(h * 0.0112))
    fval = _font(_UI_BOLD, int(h * 0.0168))
    for fx, label, value in [(0.050, "REPORT NUMBER", report_number or "—"),
                             (0.215, "REVISION", f"Rev {revision or '00'}"),
                             (0.345, "ISSUE DATE", issue_date or "—")]:
        _track(d, (X(fx), Y(0.9175)), label, flab, (128, 190, 112), w * 0.0016)
        d.text((X(fx), Y(0.9395)), value, font=fval, fill=WHITE)
    for dx in (0.186, 0.316, 0.520):
        d.line([(X(dx), Y(0.9125)), (X(dx), Y(0.9555))], fill=(50, 74, 112),
               width=max(1, int(w * 0.0011)))

    d.polygon([(X(0.555), Y(0.9355)), (X(0.582), Y(0.9245)),
               (X(0.608), Y(0.9265)), (X(0.580), Y(0.9385)),
               (X(0.561), Y(0.9380))], fill=GREEN)
    gx, cur = X(0.632), X(0.632)
    for txt, fnt, col in [("For a ", _font(_UI_REG, int(h * 0.0158)), WHITE),
                          ("Sustainable", _font(_UI_BOLD, int(h * 0.0158)),
                           GREEN_LT),
                          (" Tomorrow", _font(_UI_REG, int(h * 0.0158)),
                           WHITE)]:
        d.text((cur, Y(0.9145)), txt, font=fnt, fill=col)
        cur += d.textlength(txt, font=fnt)
    small = _font(_UI_REG, int(h * 0.0140))
    d.text((gx, Y(0.9375)), company[0], font=small, fill=SUB)
    d.text((gx, Y(0.9545)), company[1], font=small, fill=SUB)

    page.resize((W, H), Image.LANCZOS).save(out_path, "PNG", dpi=(DPI, DPI))
    return out_path
