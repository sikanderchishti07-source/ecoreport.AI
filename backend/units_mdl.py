"""Gas units and method detection limits.

Two independent safeguards on the numbers that go into a stamped report:

UNITS
-----
Analysers natively output ppb or ppm; NCEC limits are expressed in µg/m³ at
25 °C and 101.3 kPa. A campaign declares the units of its uploaded file and
gas readings are converted on ingest, so the stored data is always µg/m³.
A plausibility check flags files whose magnitudes look wrong for the declared
units, which catches the dangerous silent case: ppb data uploaded as µg/m³
(or the reverse) would shift every value — and every compliance verdict — by
roughly a factor of 2.5.

DETECTION LIMITS
----------------
Below its method detection limit (MDL) an analyser still outputs numbers, but
they are instrument noise rather than measurement. Reporting them as measured
values is indefensible. Following USEPA practice, values below the MDL are:
  * reported in tables as "<MDL" rather than raw digits, and
  * substituted with MDL/2 in every calculation.
Particulates (gravimetric/beta) are excluded — MDL applies to gas analysers.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

# Molar masses (g/mol) of the gases reported in µg/m³
MOLAR_MASS: Dict[str, float] = {
    "SO2": 64.066,
    "NO": 30.006,
    "NO2": 46.006,
    "NOx": 46.006,     # reported as NO2 equivalent, per convention
    "CO": 28.010,
    "H2S": 34.081,
    "O3": 47.997,
}

# Gas fields only — particulate matter is measured directly in µg/m³
GAS_FIELDS = tuple(MOLAR_MASS.keys())

# Molar volume of an ideal gas at 25 °C and 101.3 kPa (L/mol), the reference
# conditions stated in the NCEC 2020 standards.
MOLAR_VOLUME_25C = 24.45

SUPPORTED_UNITS = ("ugm3", "ppb", "ppm")
UNIT_LABELS = {
    "ugm3": "µg/m³",
    "ppb": "ppb (parts per billion)",
    "ppm": "ppm (parts per million)",
}


def to_ugm3(value: float, pollutant: str, units: str) -> float:
    """Convert a gas concentration to µg/m³ at 25 °C / 101.3 kPa."""
    if units == "ugm3" or pollutant not in MOLAR_MASS:
        return value
    factor = MOLAR_MASS[pollutant] / MOLAR_VOLUME_25C     # ppb -> µg/m³
    if units == "ppb":
        return value * factor
    if units == "ppm":
        return value * factor * 1000.0
    return value


# Typical ambient magnitudes in µg/m³, used only to sanity-check the declared
# units. Deliberately wide: this flags order-of-magnitude mistakes, not
# unusual-but-real air quality.
_PLAUSIBLE_UGM3 = {
    "SO2": (0.5, 800.0),
    "NO2": (0.5, 500.0),
    "NO": (0.5, 500.0),
    "NOx": (0.5, 800.0),
    "O3": (1.0, 400.0),
    "H2S": (0.2, 200.0),
    "CO": (50.0, 40000.0),
}


def check_units_plausible(medians: Dict[str, float],
                          units: str) -> Optional[str]:
    """Compare per-gas medians (already converted to µg/m³) with typical
    ambient magnitudes. Returns a warning string, or None when nothing looks
    wrong. Never blocks an upload — the operator decides."""
    suspicious = []
    for pol, med in medians.items():
        rng = _PLAUSIBLE_UGM3.get(pol)
        if not rng or med is None or med <= 0:
            continue
        low, high = rng
        if med < low / 10.0:
            suspicious.append(f"{pol} median {med:.2f} µg/m³ is unusually low")
        elif med > high * 3.0:
            suspicious.append(f"{pol} median {med:,.0f} µg/m³ is unusually high")
    if not suspicious:
        return None
    hint = ("The file was read as µg/m³ — if the analyser exports ppb, set the "
            "campaign's gas units to ppb and re-upload."
            if units == "ugm3" else
            f"The file was read as {UNIT_LABELS.get(units, units)} and "
            f"converted to µg/m³ — check the campaign's gas units setting.")
    return "Please check units: " + "; ".join(suspicious) + ". " + hint


# ---------------------------------------------------------------------------
# Detection limits
# ---------------------------------------------------------------------------
def mdl_map(instruments) -> Dict[str, float]:
    """Build {pollutant: MDL in µg/m³} from a campaign's instrument rows.

    An instrument row may cover several parameters ("NO, NO2, NOX"), so the
    MDL is applied to each gas named in the row. Rows without an MDL, and all
    particulate rows, are ignored.
    """
    out: Dict[str, float] = {}
    for inst in instruments or []:
        d = inst if isinstance(inst, dict) else inst.model_dump()
        raw = d.get("mdl_ugm3")
        if raw in (None, ""):
            continue
        try:
            mdl = float(raw)
        except (TypeError, ValueError):
            continue
        if mdl <= 0:
            continue
        text = str(d.get("parameter", "")).upper()
        for gas in GAS_FIELDS:
            token = gas.upper()
            if token in text.replace("PM2.5", "").replace("PM10", ""):
                out[gas] = mdl
    return out


def apply_mdl(value: Optional[float], mdl: Optional[float]
              ) -> Tuple[Optional[float], bool]:
    """Return (value_for_calculations, was_below_mdl).

    Below-MDL values are substituted with MDL/2 (USEPA convention) rather than
    discarded, so averages remain conservative and defensible.
    """
    if value is None or mdl is None or mdl <= 0:
        return value, False
    if value < mdl:
        return mdl / 2.0, True
    return value, False


def format_with_mdl(value: Optional[float], mdl: Optional[float],
                    decimals: int = 1) -> Optional[str]:
    """Table display: '<2.0' when below the detection limit, else the number."""
    if value is None:
        return None
    if mdl and value < mdl:
        return f"<{mdl:.{decimals}f}"
    return f"{value:,.{decimals}f}"
