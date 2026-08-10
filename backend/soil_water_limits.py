"""Soil and water limit tables — transcribed from the primary regulations.

Two Executive Regulations issued under the Environmental Law, Royal Decree
No. (m/165) dated 19/11/1441H:

  * Executive Regulation for the Prevention and Remediation of Soil Pollution
    - Article (1)  defines coarse soil (grains >= 75 um) and soft soil (< 75 um)
    - Article (4)  makes Appendix (1) the soil protection standard, and states
                   that the standards do not apply where the natural
                   concentration in the soil already exceeds them
    - Appendix (1) the limit table, by particle size and by land use

  * Executive Regulations for the Protection of Aqueous Media from Pollution
    - Article (4)  classifies water bodies (Table 1) and adopts Appendix (1)
    - Article (6)  adopts Appendices (2) and (3) for treated wastewater
    - Appendix (1) ambient water quality standards
    - Appendix (2) treated wastewater before discharge to coastal/marine water
    - Appendix (3) treated wastewater before discharge to soil, land, or
                   surface water

The Arabic original prevails over the English translation in both documents.

Three properties of these tables that the air and noise engines never had to
deal with, and which the whole module is shaped around:

1. A limit is not one number. A soil limit is chosen by particle size, land
   use and depth; an ambient water limit is chosen by the class of the water
   body. Get the context wrong and the report is judged against the wrong
   standard while looking entirely correct.

2. Not every limit is a ceiling. Dissolved oxygen is a minimum. pH is a
   range. Judging those with "over the limit is bad" passes a dead sample.

3. Some cells are not numbers at all. NBL means natural background level:
   there is no fixed figure and nothing can be judged until the background
   has been measured. Others are blank in the regulation, or were not
   legible in the published PDF. Every one of those returns no verdict.

Nothing in this module guesses. A limit that cannot be established returns
`assessable=False` with a reason, and the report prints the result with no
compliance conclusion. A blank verdict is recoverable; a wrongly issued
COMPLIANT is not.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Context vocabulary
# ---------------------------------------------------------------------------

# Appendix (1) of the soil regulation, column order left to right.
LAND_USES: Tuple[str, ...] = (
    "natural", "agricultural", "residential", "commercial", "industrial",
)
LAND_USE_LABELS: Dict[str, str] = {
    "natural": "Natural area",
    "agricultural": "Agricultural",
    "residential": "Residential / gardens",
    "commercial": "Commercial",
    "industrial": "Industrial",
}

# Article (1): coarse soil is sand and gravel, grains >= 75 um. Soft soil is
# silt and clay, grains < 75 um.
PARTICLE_SIZES: Tuple[str, ...] = ("coarse", "soft")
PARTICLE_SIZE_LABELS: Dict[str, str] = {
    "coarse": "Coarse soil (sand and gravel, grains >= 75 um)",
    "soft": "Soft soil (silt and clay, grains < 75 um)",
}

# Appendix (1) splits the hydrocarbon rows by depth. Every other row applies
# to both.
DEPTHS: Tuple[str, ...] = ("topsoil", "subsurface")
DEPTH_LABELS: Dict[str, str] = {
    "topsoil": "Topsoil / surface",
    "subsurface": "Subsurface",
}

# Table (1) of the water regulation. All coastal water is "public" unless a
# competent authority has declared it high-value or industrial — that is a
# declaration, not something observable from the sample.
WATER_MEDIA: Tuple[str, ...] = (
    "coastal_public", "coastal_high_value", "coastal_industrial",
    "surface", "ground",
)
WATER_MEDIA_LABELS: Dict[str, str] = {
    "coastal_public": "Coastal water — public",
    "coastal_high_value": "Coastal water — high-value",
    "coastal_industrial": "Coastal water — industrial",
    "surface": "Surface water (unsuitable for drinking)",
    "ground": "Ground water (potable unless NBL specified)",
}

# Appendix (2) and Appendix (3): where the treated wastewater is going.
DISCHARGE_DESTINATIONS: Tuple[str, ...] = (
    "coastal_marine", "soil_land", "surface_water",
)
DISCHARGE_DESTINATION_LABELS: Dict[str, str] = {
    "coastal_marine": "Coastal and marine waters (Appendix 2)",
    "soil_land": "Soil or land (Appendix 3)",
    "surface_water": "Surface water (Appendix 3)",
}

# Averaging interval given in the "Average Interval" column of Appendices
# (2) and (3). A single grab sample can only ever be judged against the
# bracketed maximum-for-any-sample figure — never against a 30-day or annual
# average it does not have the data to form.
INTERVALS: Tuple[str, ...] = ("sample", "30_days", "annual_monthly")
INTERVAL_LABELS: Dict[str, str] = {
    "sample": "Any single sample",
    "30_days": "30-day average",
    "annual_monthly": "Annual average of monthly samples",
}

# Sentinel for a cell the regulation gives as NBL — natural background level.
NBL = "NBL"


# ---------------------------------------------------------------------------
# What a lookup returns
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Limit:
    """The outcome of asking for one limit in one context.

    `assessable` is the only field the caller must branch on. When it is
    False there is no verdict to give and `reason` says why, in words fit to
    print in a report.
    """
    analyte: str
    unit: str
    assessable: bool
    reason: Optional[str] = None
    # direction: "max" (result must not exceed), "min" (result must not fall
    # below), or "range" (result must sit between low and high inclusive).
    direction: str = "max"
    value: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    source: str = ""
    note: Optional[str] = None

    def verdict(self, result: Optional[float]) -> str:
        """complies | exceeds | not_assessed.

        A result of None (not determined, or reported below the laboratory
        limit of quantification) is never called an exceedance.
        """
        if not self.assessable or result is None:
            return "not_assessed"
        if self.direction == "min":
            return "complies" if result >= (self.value or 0.0) else "exceeds"
        if self.direction == "range":
            if self.low is None or self.high is None:
                return "not_assessed"
            return "complies" if self.low <= result <= self.high else "exceeds"
        if self.value is None:
            return "not_assessed"
        return "complies" if result <= self.value else "exceeds"

    def printed(self) -> str:
        """The limit as it should appear in the report's limit column."""
        if not self.assessable:
            return "No limit"
        if self.direction == "range":
            return f"{_num(self.low)} \u2013 {_num(self.high)}"
        if self.direction == "min":
            return f"Min {_num(self.value)}"
        return _num(self.value)


def _num(v: Optional[float]) -> str:
    if v is None:
        return "\u2014"
    if v == int(v) and abs(v) >= 1:
        return f"{int(v):,}"
    return f"{v:g}"


# ---------------------------------------------------------------------------
# Soil — Appendix (1) of the soil regulation
# ---------------------------------------------------------------------------
# Each row: five values for coarse soil and five for soft soil, in LAND_USES
# order. None means the regulation leaves that cell blank -> no verdict.
# `depth` is set only on the rows Appendix (1) splits by depth.
SoilRow = Dict[str, object]
SOIL_LIMITS: List[SoilRow] = []


def _s(name: str, group: str, unit: str,
       coarse: Sequence[Optional[float]], soft: Sequence[Optional[float]],
       depth: Optional[str] = None, direction: str = "max",
       note: Optional[str] = None) -> None:
    assert len(coarse) == 5 and len(soft) == 5, name
    SOIL_LIMITS.append({
        "analyte": name, "group": group, "unit": unit,
        "coarse": tuple(coarse), "soft": tuple(soft),
        "depth": depth, "direction": direction, "note": note,
    })


def _both(v):
    return (v, v, v, v, v)


# --- general ---------------------------------------------------------------
_s("pH (in 0.01M CaCl2)", "general", "pH units", _both(8.5), _both(8.5))
_s("Cyanide (free)", "general", "mg/kg", (0.9, 0.9, 0.9, 8, 8), (0.9, 0.9, 0.9, 8, 8))
_s("Fluoride", "general", "mg/kg", (200, 200, 200, 2000, 2000), (200, 200, 200, 2000, 2000))
_s("Sulphur (elemental)", "general", "mg/kg", _both(500), _both(500))

# --- minerals --------------------------------------------------------------
_s("Antimony (Sb)", "minerals", "mg/kg", (20, 20, 20, 40, 40), (20, 20, 20, 40, 40))
_s("Arsenic, inorganic (As)", "minerals", "mg/kg", (17, 17, 17, 26, 26), (17, 17, 17, 26, 26))
_s("Barium, non-barite (Ba)", "minerals", "mg/kg", (750, 750, 500, 2000, 2000), (750, 750, 500, 2000, 2000))
_s("Barite-barium", "minerals", "mg/kg",
   (10000, 10000, 10000, 15000, 140000), (10000, 10000, 10000, 15000, 140000))
_s("Beryllium (Be)", "minerals", "mg/kg", (5, 5, 5, 8, 8), (5, 5, 5, 8, 8))
_s("Boron, saturated phase extract (B)", "minerals", "mg/kg",
   (3.3, 3.3, 3.3, 5, 5), (3.3, 3.3, 3.3, 5, 5))
_s("Cadmium (Cd)", "minerals", "mg/kg", (3.8, 1.4, 10, 22, 22), (3.8, 1.4, 10, 22, 22))
_s("Chromium, hexavalent (Cr VI)", "minerals", "mg/kg",
   (0.4, 0.4, 0.4, 1.4, 1.4), (0.4, 0.4, 0.4, 1.4, 1.4))
_s("Chromium, total (Cr)", "minerals", "mg/kg", (64, 64, 64, 87, 87), (64, 64, 64, 87, 87))
_s("Cobalt (Co)", "minerals", "mg/kg", (20, 20, 20, 300, 300), (20, 20, 20, 300, 300))
_s("Copper (Cu)", "minerals", "mg/kg", (63, 63, 63, 91, 91), (63, 63, 63, 91, 91))
_s("Lead (Pb)", "minerals", "mg/kg", (70, 70, 140, 260, 600), (70, 70, 140, 260, 600))
_s("Mercury, inorganic (Hg)", "minerals", "mg/kg", (12, 6.6, 6.6, 24, 50), (12, 6.6, 6.6, 24, 50))
_s("Molybdenum (Mo)", "minerals", "mg/kg", (4, 4, 4, 40, 40), (4, 4, 4, 40, 40))
_s("Nickel (Ni)", "minerals", "mg/kg", (45, 45, 45, 89, 89), (45, 45, 45, 89, 89))
_s("Selenium (Se)", "minerals", "mg/kg", (1, 1, 1, 2.9, 2.9), (1, 1, 1, 2.9, 2.9))
_s("Silver (Ag)", "minerals", "mg/kg", (20, 20, 20, 40, 40), (20, 20, 20, 40, 40))
_s("Thallium (Tl)", "minerals", "mg/kg", _both(1), _both(1))
_s("Tin (Sn)", "minerals", "mg/kg", (5, 5, 5, 300, 300), (5, 5, 5, 300, 300))
_s("Uranium (U)", "minerals", "mg/kg", (33, 23, 23, 33, 300), (33, 23, 23, 33, 300))
_s("Vanadium (V)", "minerals", "mg/kg", _both(130), _both(130))
_s("Zinc (Zn)", "minerals", "mg/kg", (200, 200, 200, 360, 360), (200, 200, 200, 360, 360))

# --- hydrocarbons: BTEX ----------------------------------------------------
_s("Benzene", "hydrocarbons", "mg/kg",
   (0.078, 0.073, 0.073, 0.078, 0.078), _both(0.046), depth="topsoil")
_s("Benzene", "hydrocarbons", "mg/kg", _both(0.078), _both(0.046), depth="subsurface")
_s("Toluene", "hydrocarbons", "mg/kg", _both(0.12), _both(0.52), depth="topsoil")
_s("Toluene", "hydrocarbons", "mg/kg", _both(0.12), _both(0.52), depth="subsurface")
_s("Ethylbenzene", "hydrocarbons", "mg/kg",
   (0.14, 0.018, 0.14, 0.14, 0.14), _both(0.073), depth="topsoil")
_s("Ethylbenzene", "hydrocarbons", "mg/kg", _both(0.14), _both(0.073), depth="subsurface")
_s("Xylenes", "hydrocarbons", "mg/kg",
   (1.9, 0.003, 1.9, 1.9, 1.9), _both(0.99), depth="topsoil")
_s("Xylenes", "hydrocarbons", "mg/kg", _both(1.9), _both(0.99), depth="subsurface")
_s("Styrene", "hydrocarbons", "mg/kg", _both(0.8), _both(0.68))

# --- hydrocarbons: TPH fractions ------------------------------------------
_s("F1: C6 to C10", "tph", "mg/kg",
   (210, 24, 24, 270, 270), (210, 210, 210, 320, 320), depth="topsoil")
_s("F2: C10 to C16", "tph", "mg/kg",
   (150, 130, 130, 260, 260), (150, 150, 150, 260, 260), depth="topsoil")
_s("F3: C16 to C34", "tph", "mg/kg",
   (300, 300, 300, 1700, 1700), (1300, 1300, 1300, 2500, 2500), depth="topsoil")
_s("F4: C34 to C50", "tph", "mg/kg",
   (2800, 2800, 2800, 3300, 3300), (5600, 5600, 5600, 6600, 6600), depth="topsoil")
_s("F1: C6 to C10", "tph", "mg/kg",
   (420, 30, 30, 440, 440), (420, 420, 420, 640, 640), depth="subsurface")
_s("F2: C10 to C16", "tph", "mg/kg",
   (300, 160, 160, 520, 520), (300, 300, 300, 520, 520), depth="subsurface")
_s("F3: C16 to C34", "tph", "mg/kg",
   (600, 600, 600, 3400, 3400), (2600, 2600, 2600, 4300, 4300), depth="subsurface")
_s("F4: C34 to C50", "tph", "mg/kg",
   (5600, 5600, 5600, 6600, 6600), _both(10000), depth="subsurface")

# --- PAHs ------------------------------------------------------------------
_s("Acenaphthene", "pah", "mg/kg", _both(0.38), _both(0.32))
_s("Anthracene", "pah", "mg/kg", _both(0.0056), _both(0.0046))
_s("Fluoranthene", "pah", "mg/kg", _both(0.039), _both(0.032))
_s("Fluorene", "pah", "mg/kg", _both(0.34), _both(0.29))
_s("Naphthalene", "pah", "mg/kg", _both(0.017), _both(0.014))
_s("Phenanthrene", "pah", "mg/kg", _both(0.061), _both(0.051))
_s("Pyrene", "pah", "mg/kg", _both(0.04), _both(0.034))
_s("Carcinogenic PAHs", "pah", "mg/kg", _both(1), _both(1),
   note="Appendix (1) qualifies the soft soil agricultural cell as IACR < 1.")
_s("Benz[a]anthracene", "pah", "mg/kg", _both(0.083), _both(0.07))
_s("Benzo[b+j]fluoranthene", "pah", "mg/kg",
   (6.2, 6.2, None, None, None), (6.2, 6.2, None, None, None))
_s("Benzo[k]fluoranthene", "pah", "mg/kg",
   (6.2, 6.2, None, None, None), (6.2, 6.2, None, None, None))
_s("Benzo[a]pyrene", "pah", "mg/kg",
   (0.6, 0.6, 0.77, 0.77, 0.77), (0.6, 0.6, 0.7, 0.7, 0.7))
_s("Chrysene", "pah", "mg/kg",
   (6.2, 6.2, None, None, None), (6.2, 6.2, None, None, None))

# --- halogenated aliphatic and aromatic compounds --------------------------
_s("Vinyl chloride", "halogenated", "mg/kg",
   (0.02, 0.00034, 0.00034, 0.0043, 0.0043), (0.014, 0.0083, 0.0083, 0.014, 0.014))
_s("1,1-Dichloroethene", "halogenated", "mg/kg",
   (0.24, 0.021, 0.021, 0.24, 0.24), _both(0.15))
_s("Trichloroethene (TCE)", "halogenated", "mg/kg",
   (0.081, 0.012, 0.012, 0.081, 0.081), _both(0.054))
_s("Tetrachloroethene", "halogenated", "mg/kg",
   (0.46, 0.018, 0.018, 0.22, 0.22), _both(0.26))
_s("1,2-Dichloroethane", "halogenated", "mg/kg",
   (0.041, 0.0027, 0.0027, 0.033, 0.033), (0.025, 0.0062, 0.025, 0.025, 0.15))
_s("Dichloromethane", "halogenated", "mg/kg",
   (0.095, 0.048, 0.095, 0.095, 0.095), (0.1, 0.052, 0.1, 0.1, 0.1))
_s("Trichloromethane (chloroform)", "halogenated", "mg/kg", _both(0.003), _both(0.0029))
_s("Tetrachloromethane", "halogenated", "mg/kg",
   (0.062, 0.00056, 0.00057, 0.0069, 0.0069), (0.037, 0.013, 0.013, 0.037, 0.037))
_s("Dibromochloromethane", "halogenated", "mg/kg",
   (1.5, 0.12, 0.27, 1.5, 1.5), (0.91, 0.12, 0.91, 0.91, 0.91))
_s("Chlorobenzene", "halogenated", "mg/kg",
   (1.1, 0.018, 0.018, 0.22, 0.22), (0.61, 0.39, 0.39, 0.61, 0.61))
_s("1,2-Dichlorobenzene", "halogenated", "mg/kg", _both(0.18), _both(0.097))
_s("1,4-Dichlorobenzene", "halogenated", "mg/kg", _both(0.098), _both(0.051))
_s("1,2,3-Trichlorobenzene", "halogenated", "mg/kg",
   (0.31, 0.26, 0.26, 0.31, 0.31), _both(0.26))
_s("1,2,4-Trichlorobenzene", "halogenated", "mg/kg",
   (0.93, 0.23, 0.23, 0.93, 0.93), _both(0.78))
_s("1,3,5-Trichlorobenzene", "halogenated", "mg/kg",
   (3.6, 0.13, 0.13, 1.3, 1.3), _both(1.9))
_s("1,2,3,4-Tetrachlorobenzene", "halogenated", "mg/kg", _both(0.05), _both(0.042))
_s("1,2,3,5-Tetrachlorobenzene", "halogenated", "mg/kg",
   (0.7, 0.1, 0.1, 0.7, 0.7), _both(0.37))
_s("1,2,4,5-Tetrachlorobenzene", "halogenated", "mg/kg",
   (0.37, 0.052, 0.052, 0.37, 0.37), _both(0.19))
_s("Pentachlorobenzene", "halogenated", "mg/kg", _both(4.5), _both(3.7))
_s("Hexachlorobenzene", "halogenated", "mg/kg",
   (7, 0.5, 0.5, 6, 6), (3.6, 0.8, 3.6, 3.6, 3.6))
_s("2,4-Dichlorophenol", "halogenated", "mg/kg", _both(0.0034), _both(0.0029))
_s("2,4,6-Trichlorophenol", "halogenated", "mg/kg", _both(0.37), _both(0.19))
_s("2,3,4,6-Tetrachlorophenol", "halogenated", "mg/kg", _both(0.047), _both(0.039))
_s("Pentachlorophenol", "halogenated", "mg/kg", _both(0.029), _both(0.024))
_s("Dioxins and furans", "halogenated", "mg/kg",
   (0.00025, 0.000004, 0.000004, 0.000004, 0.000004),
   (0.00025, 0.000004, 0.000004, 0.000004, 0.000004))
_s("Polychlorinated biphenyls (PCBs)", "halogenated", "mg/kg",
   (1.3, 13, 22, 33, 33), (1.3, 1.3, 22, 33, 33))

# --- pesticides ------------------------------------------------------------
_s("Aldicarb", "pesticides", "mg/kg",
   (0.065, 0.012, 0.065, 0.065, 0.065), (0.041, 0.012, 0.041, 0.041, 0.041))
_s("Aldrin", "pesticides", "mg/kg", (11, 3.4, 3.4, 5.1, 11), (5.9, 3.4, 3.4, 5.1, 5.9))
_s("Atrazine and metabolites", "pesticides", "mg/kg", _both(0.01), _both(0.0088))
_s("Azinphos-methyl", "pesticides", "mg/kg", _both(0.75), _both(0.41))
_s("Bendiocarb", "pesticides", "mg/kg", _both(0.21), _both(0.14))
_s("Bromacil", "pesticides", "mg/kg", _both(0.009), _both(0.009))
_s("Bromoxynil", "pesticides", "mg/kg", _both(0.052), _both(0.044))
_s("Carbaryl", "pesticides", "mg/kg", _both(3.6), _both(1.9))
_s("Carbofuran", "pesticides", "mg/kg",
   (1.2, 0.089, 1.2, 1.2, 1.2), (0.68, 0.082, 0.68, 0.68, 0.68))
_s("Chlorothalonil", "pesticides", "mg/kg", _both(0.01), _both(0.0084))
_s("Chlorpyrifos", "pesticides", "mg/kg",
   (95, 3.8, 95, 95, 95), (49, 3.2, 49, 49, 49))
_s("Cyanazine", "pesticides", "mg/kg",
   (0.21, 0.032, 0.21, 0.21, 0.21), (0.12, 0.029, 0.12, 0.12, 0.12))
_s("2,4-Dichlorophenoxyacetic acid (2,4-D)", "pesticides", "mg/kg",
   (0.67, 0.1, 0.67, 0.67, 0.67), (0.43, 0.1, 0.43, 0.43, 0.43))
_s("Dichlorodiphenyltrichloroethane (DDT)", "pesticides", "mg/kg",
   (0.7, 0.7, 12, 12, 12), (0.7, 0.7, 12, 12, 12))
_s("Diazinon", "pesticides", "mg/kg", _both(4.2), _both(2.2))
_s("Dicamba", "pesticides", "mg/kg",
   (0.79, 0.12, 0.79, 0.79, 0.79), (0.5, 0.12, 0.5, 0.5, 0.5))
_s("Dichlofop-methyl", "pesticides", "mg/kg",
   (2.4, 0.095, 2.4, 2.4, 2.4), (2, 0.079, 2, 2, 2))
_s("Dieldrin", "pesticides", "mg/kg", _both(1.1), _both(0.59))
_s("Dimethoate", "pesticides", "mg/kg",
   (0.0055, 0.0027, 0.0055, 0.0055, 0.0055), (0.0058, 0.0028, 0.0058, 0.0058, 0.0058))
_s("Dinoseb", "pesticides", "mg/kg",
   (5.5, 1.7, 5.5, 5.5, 5.5), (2.8, 1.4, 2.8, 2.8, 2.8))
_s("Diquat", "pesticides", "mg/kg", _both(21), _both(11))
_s("Diuron", "pesticides", "mg/kg", _both(3.5), _both(1.9))
_s("Endosulfan", "pesticides", "mg/kg", _both(0.0015), _both(0.0013))
_s("Endrin", "pesticides", "mg/kg", _both(4.7), _both(2.4))
_s("Glyphosate", "pesticides", "mg/kg", _both(0.049), _both(0.054))
_s("Heptachlor epoxide", "pesticides", "mg/kg",
   (0.076, 0.01, 0.01, 0.076, 0.076), _both(0.039))
_s("Lindane", "pesticides", "mg/kg",
   (0.6, 0.13, 0.6, 0.6, 0.6), (0.31, 0.11, 0.31, 0.31, 0.31))
_s("Linuron", "pesticides", "mg/kg", _both(0.059), _both(0.051))
_s("Malathion", "pesticides", "mg/kg", _both(1.3), _both(0.82))
_s("MCPA", "pesticides", "mg/kg",
   (0.66, 0.025, 0.66, 0.66, 0.66), (0.42, 0.026, 0.42, 0.42, 0.42))
_s("Methoxychlor", "pesticides", "mg/kg", _both(0.056), _both(0.046))
_s("Metolachlor", "pesticides", "mg/kg", _both(0.055), _both(0.048))
_s("Metribuzin", "pesticides", "mg/kg",
   (0.028, 0.014, 0.028, 0.028, 0.028), (0.024, 0.012, 0.024, 0.024, 0.024))
_s("Paraquat (as dichloride)", "pesticides", "mg/kg", _both(2.2), _both(1.1))
_s("Parathion", "pesticides", "mg/kg", _both(14), _both(7.2))
_s("Phorate", "pesticides", "mg/kg", _both(0.14), _both(0.075))
_s("Picloram", "pesticides", "mg/kg", _both(0.022), _both(0.024))
_s("Simazine", "pesticides", "mg/kg", _both(0.038), _both(0.033))
_s("Tebuthiuron", "pesticides", "mg/kg",
   (0.046, 0.046, 0.046, 0.6, 0.6), (0.046, 0.046, 0.046, 0.6, 0.6))
_s("Terbufos", "pesticides", "mg/kg", _both(0.15), _both(0.08))
_s("Toxaphene", "pesticides", "mg/kg", (6.3, 4.8, 4.8, 6.3, 6.3), _both(3.3))
_s("Triallate", "pesticides", "mg/kg", _both(0.0092), _both(0.0077))
_s("Trifluralin", "pesticides", "mg/kg", _both(0.045), _both(0.038))

# --- other organic compounds ----------------------------------------------
_s("Aniline", "organics", "mg/kg", _both(0.6), _both(0.36))
_s("Bis(2-ethylhexyl) phthalate", "organics", "mg/kg", _both(41), _both(34))
_s("Dibutyl phthalate", "organics", "mg/kg", _both(0.65), _both(0.54))
_s("Dichlorobenzidine", "organics", "mg/kg", _both(8.1), _both(4.2))
_s("Diethanolamine", "organics", "mg/kg", _both(3.5), _both(2))
_s("Diethylene glycol", "organics", "mg/kg", _both(15), _both(10))
_s("Diisopropanolamine", "organics", "mg/kg", _both(17), _both(14))
_s("Ethylene glycol", "organics", "mg/kg", _both(62), _both(60))
_s("Hexachlorobutadiene", "organics", "mg/kg",
   (0.031, 0.0067, 0.0067, 0.031, 0.031), _both(0.026))
_s("Methanol", "organics", "mg/kg", _both(11), _both(37))
_s("Methyl methacrylate", "organics", "mg/kg",
   (1.8, 0.1, 0.1, 1.3, 1.3), _both(1.3))
_s("Monoethanolamine", "organics", "mg/kg", _both(10), _both(20))
_s("Methyl tert-butyl ether (MTBE)", "organics", "mg/kg",
   (0.062, 0.046, 0.046, 0.062, 0.062), _both(0.044))
_s("Nonylphenol and ethoxylates", "organics", "mg/kg",
   (5.7, 5.7, 5.7, 14, 14), (5.7, 5.7, 5.7, 14, 14))
_s("Phenols", "organics", "mg/kg",
   (0.0024, 0.0012, 0.0024, 0.0024, 0.0024),
   (0.0028, 0.0014, 0.0028, 0.0028, 0.0028))
_s("Sulfolane", "organics", "mg/kg", _both(0.21), _both(0.18))
_s("Triethylene glycol", "organics", "mg/kg", _both(150), _both(100))

# --- radioactive elements --------------------------------------------------
_s("Uranium-238 series (all progeny)", "radionuclides", "Bq/g", _both(0.3), _both(0.3))
_s("Uranium-238", "radionuclides", "Bq/g", _both(10), _both(10))
_s("Thorium-230", "radionuclides", "Bq/g", _both(10), _both(10))
_s("Radium-226 (in equilibrium with progeny)", "radionuclides", "Bq/g", _both(0.3), _both(0.3))
_s("Lead-210 (in equilibrium with Bi-210 and Po-210)", "radionuclides", "Bq/g",
   _both(0.3), _both(0.3))
_s("Thorium-232 series (all progeny)", "radionuclides", "Bq/g", _both(0.3), _both(0.3))
_s("Thorium-232", "radionuclides", "Bq/g", _both(10), _both(10))
_s("Radium-228 (in equilibrium with Ac-228)", "radionuclides", "Bq/g", _both(0.3), _both(0.3))
_s("Thorium-228 (in equilibrium with progeny)", "radionuclides", "Bq/g", _both(0.3), _both(0.3))
_s("Potassium-40", "radionuclides", "Bq/g", _both(17), _both(17))

SOIL_SOURCE = ("Executive Regulation for the Prevention and Remediation of "
               "Soil Pollution, Appendix (1)")


# ---------------------------------------------------------------------------
# Water — Appendix (1), ambient water quality
# ---------------------------------------------------------------------------
# Five values in WATER_MEDIA order. A value may be a number, NBL, or None
# where the regulation leaves the cell blank. `direction` is per row.
WATER_AMBIENT: List[Dict[str, object]] = []


def _w(name: str, group: str, unit: str, values: Sequence[object],
       direction: str = "max", ranges: Optional[Sequence[object]] = None,
       note: Optional[str] = None, assessable: bool = True) -> None:
    assert len(values) == 5, name
    WATER_AMBIENT.append({
        "analyte": name, "group": group, "unit": unit,
        "values": tuple(values), "direction": direction,
        "ranges": tuple(ranges) if ranges else None,
        "note": note, "assessable": assessable,
    })


def _w5(v):
    return (v, v, v, v, v)


# --- physical --------------------------------------------------------------
_w("Colour", "physical", "\u2014", (None,) * 5, assessable=False,
   note="Appendix (1) cell not legible in the published English translation; "
        "confirm against the Arabic original before assessing.")
_w("Temperature difference (delta T)", "physical", "\u00b0C",
   (3, 2, 4, NBL, NBL),
   note="Measured at the mixing zone boundary per Appendix (5).")
_w("Total dissolved solids (TDS)", "physical", "mg/L", (NBL, NBL, NBL, 5000, NBL))
_w("Turbidity", "physical", "NTU", (3, 2, 5, 30, NBL))

# --- chemical --------------------------------------------------------------
_w("Aldrin", "chemical", "mg/L", _w5(2.2e-6))
_w("Aluminium", "chemical", "mg/L", (0.2, 0.2, 1, 0.2, 0.2))
_w("Ammonia", "chemical", "mg/L", (0.1, 0.05, 1, 0.1, 0.3))
_w("Arsenic", "chemical", "mg/L", (0.05, 0.05, 0.069, 0.15, 0.0075))
_w("Barium", "chemical", "mg/L", (0.5, 0.5, 1, 0.5, 1))
_w("Benzene", "chemical", "mg/L", (0.05, 0.05, 0.05, 0.05, 0.002))
_w("Biological oxygen demand (BOD)", "chemical", "mg/L", (15, 10, 20, 10, None))
_w("Cadmium", "chemical", "mg/L", (0.008, 0.008, 0.04, 0.000025, 0.003))
_w("Calcium", "chemical", "mg/L", _w5(NBL))
_w("Carbon tetrachloride", "chemical", "mg/L", (0.001, 0.001, 0.001, 0.002, 0.005))
_w("Chlordane", "chemical", "mg/L", (4e-6, 3.2e-7, 9e-5, 4.3e-6, 3.1e-7))
_w("Chloride", "chemical", "mg/L", _w5(NBL))
_w("Chlorine", "chemical", "mg/L", (0.0075, 0.0075, 0.013, 0.019, 0.01))
_w("Chloroform", "chemical", "mg/L", (0.13, 0.13, 0.13, 0.13, 0.06))
_w("Chromium", "chemical", "mg/L", (0.05, 0.002, 0.05, 0.05, 0.037))
_w("Cobalt", "chemical", "mg/L", (0.05, 0.05, 1, 0.05, 0.05))
_w("Chemical oxygen demand (COD)", "chemical", "mg/L", (25, 20, 40, 25, None))
_w("Copper", "chemical", "mg/L", (0.003, 0.003, 0.0135, 0.05, 1.5))
_w("Cyanide (free)", "chemical", "mg/L", (0.001, 0.001, 0.001, 0.01, 0.001))
_w("Dichlorodiphenyltrichloroethane (DDT)", "chemical", "mg/L", _w5(1.7e-5))
_w("Dieldrin", "chemical", "mg/L", _w5(4e-6))
_w("Dissolved oxygen", "chemical", "mg/L", (5, 5, 4, 5, None), direction="min",
   note="A minimum, not a ceiling. A result below the figure is an exceedance.")
_w("Endrin", "chemical", "mg/L", (6e-6, 6e-6, 6e-6, 8.6e-5, 3e-5))
_w("Fluoride", "chemical", "mg/L", (1.5, 1.5, 1.5, 0.4, 0.2))
_w("Furans", "chemical", "mg/L", _w5(1e-6))
_w("Heptachlor", "chemical", "mg/L", (5e-6, 5e-6, 5e-6, 5e-6, 5.9e-9))
_w("Hexachlorobenzene", "chemical", "mg/L", (2.9e-7, 2.9e-7, 2.9e-7, 5e-5, 2.9e-7))
_w("Iron", "chemical", "mg/L", (0.5, 0.1, 1, 0.5, 0.2))
_w("Lead", "chemical", "mg/L", (0.008, 0.005, 0.21, 0.01, 0.0075))
_w("Lindane", "chemical", "mg/L", (1.2e-5, 1.2e-5, 1.2e-5, 1.2e-5, 0.0002))
_w("Manganese", "chemical", "mg/L", (0.01, 0.01, 0.1, 0.1, 0.05))
_w("Mercury", "chemical", "mg/L", (0.0004, 0.0004, 0.0001, 0.00007, 0.00075))
_w("Mirex", "chemical", "mg/L", _w5(1e-6))
_w("Methyl tert-butyl ether (MtBE)", "chemical", "mg/L", (5, 5, 5, 10, 0.02))
_w("Nickel", "chemical", "mg/L", (0.05, 0.05, 0.2, 0.05, 0.02))
_w("Oil and grease", "chemical", "mg/L", (2, 1, 3, 3, 0))
_w("Polycyclic aromatic hydrocarbons (PAH)", "chemical", "mg/L",
   (0.003, 0.003, 0.003, 0.003, 0.0002))
_w("Polychlorinated biphenyls (PCBs)", "chemical", "mg/L", _w5(1.9e-6))
_w("Pentachlorophenol", "chemical", "mg/L", (0.00004, 0.00004, 0.005, 0.019, 0.00003))
_w("pH", "chemical", "pH units", (None,) * 5, direction="range",
   ranges=((6.5, 8.5), (6.5, 8.5), (6.5, 8.5), (6.5, 9), (6.5, 9)),
   note="A range, not a ceiling. Coastal water additionally carries a maximum "
        "delta pH at the mixing zone boundary of 0.2 (public), 0.1 "
        "(high-value) and 0.3 (industrial).")
_w("Total petroleum hydrocarbons", "chemical", "mg/L", (0.3, 0.2, 0.5, 0.3, 0.2))
_w("Phenols", "chemical", "mg/L", (0.05, 0.05, 0.1, 0.05, 0.005))
_w("Silvex (2,4,5-TP)", "chemical", "mg/L", (None, None, None, None, 0.05))
_w("Total organic carbon (TOC)", "chemical", "mg/L", (10, 10, 15, 10, NBL))
_w("Salinity", "chemical", "%", (0, 0, 3, NBL, NBL),
   note="Appendix (1) gives zero for public and high-value coastal water; "
        "read as a permitted difference from background, not an absolute.")
_w("Selenium", "chemical", "mg/L", (0.071, 0.071, 0.29, None, 0.007))
_w("Silver", "chemical", "mg/L", (0.0019, 0.0019, 0.2, 0.0032, 0.0032))
_w("Sodium", "chemical", "mg/L", (NBL, NBL, NBL, 150, 150))
_w("Sulfate", "chemical", "mg/L", (NBL, NBL, NBL, 200, NBL))
_w("Sulfide", "chemical", "mg/L", (0.002, 0.002, 1, 0.002, 0.002))
_w("Tetrachlorodibenzodioxin (TCDD)", "chemical", "mg/L", _w5(3e-8))
_w("Toluene", "chemical", "mg/L", (0.002, 0.001, 0.002, 0.002, 0.002))
_w("Toxaphene", "chemical", "mg/L", (2e-7, 2e-7, 2.1e-5, 2.1e-6, 7e-7))
_w("Trichloroethane", "chemical", "mg/L", (0.01, 0.01, 0.01, 0.01, 0.001))
_w("Vinyl chloride", "chemical", "mg/L", (0.002, 0.002, 0.002, 0.002, 0.001))
_w("Xylenes", "chemical", "mg/L", _w5(0.005))
_w("Zinc", "chemical", "mg/L", (0.08, 0.08, 0.09, 0.12, 0.02))

# --- microbiological -------------------------------------------------------
_w("Cyanobacteria", "microbiological", "mg/L", (5000, 5000, 5000, 5000, None))
_w("E. coli", "microbiological", "number / 100 mL", (500, 250, 500, 600, 0))
_w("Intestinal enterococci", "microbiological", "number / 100 mL", (200, 100, 200, 230, 0))

WATER_AMBIENT_SOURCE = ("Executive Regulations for the Protection of Aqueous "
                        "Media from Pollution, Appendix (1)")


# ---------------------------------------------------------------------------
# Water — Appendices (2) and (3), treated wastewater before discharge
# ---------------------------------------------------------------------------
# `avg` is the value for the stated averaging interval. `smax` is the
# bracketed maximum for any single sample. A grab sample is judged against
# `smax` alone; where the regulation gives no `smax`, a single sample cannot
# be judged at all.
DISCHARGE_LIMITS: List[Dict[str, object]] = []


def _d(dest: str, name: str, group: str, unit: str, interval: str,
       avg: Optional[float] = None, smax: object = None,
       direction: str = "max", low: Optional[float] = None,
       high: Optional[float] = None, note: Optional[str] = None) -> None:
    DISCHARGE_LIMITS.append({
        "destination": dest, "analyte": name, "group": group, "unit": unit,
        "interval": interval, "avg": avg, "smax": smax,
        "direction": direction, "low": low, "high": high, "note": note,
    })


# --- Appendix (2): coastal and marine waters -------------------------------
C = "coastal_marine"
_d(C, "Fat, oil and grease (FOG)", "physical", "mg/L", "sample", smax=2)
_d(C, "Turbidity", "physical", "turbidity units", "sample", smax=5)
_d(C, "Temperature difference (delta T)", "physical", "\u00b0C", "sample", smax=5)
_d(C, "Total suspended solids (TSS)", "physical", "mg/L", "30_days", avg=25, smax=40)
_d(C, "Biological oxygen demand (BOD5)", "chemical", "mg/L", "30_days", avg=10, smax=25)
_d(C, "Chemical oxygen demand (COD)", "chemical", "mg/L", "30_days", avg=20, smax=50)
_d(C, "Dissolved oxygen (DO)", "chemical", "mg/L", "sample", smax=2.0, direction="min",
   note="A minimum. A result below 2.0 mg/L is an exceedance.")
_d(C, "Ammoniacal nitrogen (NH3, NH4-N)", "chemical", "mg/L", "30_days", avg=1.9)
_d(C, "Nitrate nitrogen (NO3-N)", "chemical", "mg/L", "30_days", avg=10)
_d(C, "Phosphate (PO4)", "chemical", "mg/L", "30_days", avg=1)
_d(C, "Free chlorine", "chemical", "mg/L", "sample", smax=0.1, direction="min")
_d(C, "Phenols (total)", "chemical", "mg/L", "annual_monthly", avg=0.1)
_d(C, "pH", "chemical", "pH units", "sample", direction="range", low=6.5, high=9)
_d(C, "Aluminium (Al)", "chemical", "mg/L", "annual_monthly", avg=5)
_d(C, "Arsenic (As)", "chemical", "mg/L", "annual_monthly", avg=0.036)
_d(C, "Barium (Ba)", "chemical", "mg/L", "annual_monthly", avg=1)
_d(C, "Cyanide (CN)", "chemical", "mg/L", "annual_monthly", avg=0.05)
_d(C, "Cadmium (Cd)", "chemical", "mg/L", "30_days", avg=0.005)
_d(C, "Chromium (Cr)", "chemical", "mg/L", "annual_monthly", avg=0.01)
_d(C, "Cobalt (Co)", "chemical", "mg/L", "annual_monthly", avg=0.05)
_d(C, "Copper (Cu)", "chemical", "mg/L", "annual_monthly", avg=0.5)
_d(C, "Fluoride (F)", "chemical", "mg/L", "annual_monthly", avg=15)
_d(C, "Iron (Fe)", "chemical", "mg/L", "30_days", avg=1)
_d(C, "Mercury (Hg)", "chemical", "mg/L", "annual_monthly", avg=0.001, smax=0.005)
_d(C, "Lead (Pb)", "chemical", "mg/L", "30_days", avg=0.008)
_d(C, "Manganese (Mn)", "chemical", "mg/L", "annual_monthly", avg=0.2)
_d(C, "Nickel (Ni)", "chemical", "mg/L", "annual_monthly", avg=0.008)
_d(C, "Selenium (Se)", "chemical", "mg/L", "30_days", avg=0.07)
_d(C, "Zinc (Zn)", "chemical", "mg/L", "annual_monthly", avg=0.08)
_d(C, "Total coliform bacteria", "microbiological", "MPN / 100 mL", "30_days", avg=1000)
_d(C, "Enterococci bacteria", "microbiological", "CFU / 100 mL", "30_days", avg=35)
_d(C, "E. coli", "microbiological", "CFU / 100 mL", "30_days", avg=126)

# --- Appendix (3): soil or land, and surface water -------------------------
S, F = "soil_land", "surface_water"
_d(S, "Fat, oil and grease (FOG)", "physical", "mg/L", "sample", smax=0)
_d(F, "Fat, oil and grease (FOG)", "physical", "mg/L", "sample", smax=5)
_d(S, "Total suspended solids (TSS)", "physical", "mg/L", "30_days", avg=35, smax=50)
_d(F, "Total suspended solids (TSS)", "physical", "mg/L", "30_days", avg=25, smax=40)
_d(S, "Total dissolved solids (TDS)", "physical", "mg/L", "sample", smax=2000)
_d(F, "Total dissolved solids (TDS)", "physical", "mg/L", "sample", smax=2000)
_d(S, "Turbidity", "physical", "turbidity units", "sample", smax=5)
_d(F, "Turbidity", "physical", "turbidity units", "sample", smax=5)
_d(S, "Temperature difference (delta T)", "physical", "\u00b0C", "sample", smax=NBL)
_d(F, "Temperature difference (delta T)", "physical", "\u00b0C", "sample", smax=NBL,
   note="Natural background, provided the temperature within 15 m downstream "
        "of the discharge does not exceed 40 \u00b0C.")
_d(S, "Biological oxygen demand (BOD5)", "chemical", "mg/L", "30_days", avg=25, smax=40)
_d(F, "Biological oxygen demand (BOD5)", "chemical", "mg/L", "30_days", avg=15, smax=20)
_d(S, "Dissolved oxygen (DO)", "chemical", "mg/L", "sample", smax=NBL, direction="min")
_d(F, "Dissolved oxygen (DO)", "chemical", "mg/L", "sample", smax=2, direction="min")
_d(S, "Ammoniacal nitrogen (NH3, NH4-N)", "chemical", "mg/L", "30_days", avg=5)
_d(F, "Ammoniacal nitrogen (NH3, NH4-N)", "chemical", "mg/L", "30_days", avg=1.9)
_d(S, "Nitrate nitrogen (NO3-N)", "chemical", "mg/L", "30_days", avg=15)
_d(F, "Nitrate nitrogen (NO3-N)", "chemical", "mg/L", "30_days", avg=10)
_d(S, "Phosphate (PO4)", "chemical", "mg/L", "30_days", avg=30)
_d(F, "Phosphate (PO4)", "chemical", "mg/L", "30_days", avg=20)
_d(S, "Free chlorine", "chemical", "mg/L", "sample", direction="range", low=0.1, high=0.5)
_d(F, "Free chlorine", "chemical", "mg/L", "sample", direction="range", low=0.1, high=0.5)
_d(S, "Phenols (total)", "chemical", "mg/L", "annual_monthly", avg=0.002)
_d(F, "Phenols (total)", "chemical", "mg/L", "annual_monthly", avg=0.002)
_d(S, "pH", "chemical", "pH units", "sample", direction="range", low=6, high=8.4)
_d(F, "pH", "chemical", "pH units", "sample", direction="range", low=6, high=8.4)
for _dest, _v in ((S, 5), (F, 5)):
    _d(_dest, "Aluminium (Al)", "chemical", "mg/L", "annual_monthly", avg=_v)
for _dest in (S, F):
    _d(_dest, "Arsenic (As)", "chemical", "mg/L", "annual_monthly", avg=0.1)
    _d(_dest, "Beryllium (Be)", "chemical", "mg/L", "annual_monthly", avg=0.1)
    _d(_dest, "Boron (B)", "chemical", "mg/L", "annual_monthly", avg=0.75)
    _d(_dest, "Chromium (Cr)", "chemical", "mg/L", "annual_monthly", avg=0.1)
    _d(_dest, "Cobalt (Co)", "chemical", "mg/L", "annual_monthly", avg=0.05)
    _d(_dest, "Fluoride (F)", "chemical", "mg/L", "annual_monthly", avg=1)
    _d(_dest, "Iron (Fe)", "chemical", "mg/L", "annual_monthly", avg=5)
    _d(_dest, "Mercury (Hg)", "chemical", "mg/L", "annual_monthly", avg=0.001)
    _d(_dest, "Lead (Pb)", "chemical", "mg/L", "annual_monthly", avg=0.1)
    _d(_dest, "Lithium (Li)", "chemical", "mg/L", "annual_monthly", avg=2.5)
    _d(_dest, "Manganese (Mn)", "chemical", "mg/L", "annual_monthly", avg=0.2)
    _d(_dest, "Molybdenum (Mo)", "chemical", "mg/L", "annual_monthly", avg=0.01)
    _d(_dest, "Nickel (Ni)", "chemical", "mg/L", "annual_monthly", avg=0.2)
    _d(_dest, "Selenium (Se)", "chemical", "mg/L", "annual_monthly", avg=0.02)
    _d(_dest, "Vanadium (V)", "chemical", "mg/L", "annual_monthly", avg=0.1)
_d(S, "Cadmium (Cd)", "chemical", "mg/L", "30_days", avg=0.1)
_d(F, "Cadmium (Cd)", "chemical", "mg/L", "30_days", avg=0.01)
_d(S, "Copper (Cu)", "chemical", "mg/L", "annual_monthly", avg=0.4)
_d(F, "Copper (Cu)", "chemical", "mg/L", "annual_monthly", avg=0.2)
_d(S, "Zinc (Zn)", "chemical", "mg/L", "annual_monthly", avg=4)
_d(F, "Zinc (Zn)", "chemical", "mg/L", "annual_monthly", avg=2)
_d(S, "Total coliform bacteria", "microbiological", "MPN / 100 mL", "30_days", avg=2000)
_d(F, "Total coliform bacteria", "microbiological", "MPN / 100 mL", "30_days", avg=1000)
_d(S, "Viable oval nematode", "microbiological", "live ova / L", "30_days", avg=1)
_d(F, "Viable oval nematode", "microbiological", "live ova / L", "30_days", avg=1)

DISCHARGE_SOURCE = {
    "coastal_marine": ("Executive Regulations for the Protection of Aqueous "
                       "Media from Pollution, Appendix (2)"),
    "soil_land": ("Executive Regulations for the Protection of Aqueous Media "
                  "from Pollution, Appendix (3)"),
    "surface_water": ("Executive Regulations for the Protection of Aqueous "
                      "Media from Pollution, Appendix (3)"),
}


# ---------------------------------------------------------------------------
# Analyte library — the master list a campaign's parameter profile is drawn
# from. Names, default units and the usual laboratory method, taken from
# BSA's own certificate of analysis templates.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Analyte:
    key: str            # stable identifier used in stored results
    name: str           # printed name
    media: Tuple[str, ...]   # "water" | "soil" | "sediment"
    group: str
    unit: str
    method: Optional[str] = None
    aliases: Tuple[str, ...] = field(default_factory=tuple)


def _a(key, name, media, group, unit, method=None, aliases=()):
    return Analyte(key=key, name=name, media=tuple(media), group=group,
                   unit=unit, method=method, aliases=tuple(aliases))


ANALYTES: Tuple[Analyte, ...] = (
    # --- field / physicochemical, water --------------------------------
    _a("ph", "pH", ("water", "soil", "sediment"), "physicochemical", "pH units",
       "APHA 4500-H+B"),
    _a("temperature", "Temperature", ("water",), "physicochemical", "\u00b0C", "Aqua Troll 500"),
    _a("tds", "Total dissolved solids", ("water",), "physicochemical", "mg/L", "Aqua Troll 500",
       ("TDS",)),
    _a("do", "Dissolved oxygen", ("water",), "physicochemical", "mg/L", "Aqua Troll 500",
       ("DO",)),
    _a("conductivity", "Conductivity", ("water", "soil"), "physicochemical", "mS/cm",
       "APHA 2520 B", ("EC",)),
    _a("salinity", "Salinity", ("water",), "physicochemical", "PSU", "Aqua Troll 500"),
    _a("turbidity", "Turbidity", ("water",), "physicochemical", "NTU", "Aqua Troll 500"),
    _a("cod", "Chemical oxygen demand", ("water",), "chemical", "mg/L", "APHA 5220 D", ("COD",)),
    _a("bod5", "Biological oxygen demand (BOD5)", ("water",), "chemical", "mg/L",
       "APHA 5210 B", ("BOD",)),
    _a("hardness", "Total hardness as CaCO3", ("water",), "chemical", "mg/L", "APHA 2340"),
    _a("alkalinity", "Total alkalinity as CaCO3", ("water",), "chemical", "mg/L", "APHA 5320 B"),
    _a("bicarbonate", "Bicarbonate", ("water",), "chemical", "mg/L", "Method 310.2"),
    _a("carbonate", "Carbonate", ("water", "soil"), "chemical", "mg/L", "APHA 5320 B"),
    _a("bromate", "Bromate", ("water",), "chemical", "mg/L", "US EPA 300.1"),
    _a("bromide", "Bromide (Br-)", ("water",), "chemical", "mg/L", "US EPA 300.1"),
    _a("chloride", "Chloride (Cl-)", ("water", "soil"), "chemical", "mg/L", "US EPA 300.1"),
    _a("free_chlorine", "Free chlorine", ("water",), "chemical", "mg/L", "US EPA 300.1"),
    _a("cyanide_free", "Cyanide (free)", ("water", "soil"), "chemical", "mg/L",
       "APHA 5520 CN", ("CN",)),
    _a("fluoride", "Fluoride (F)", ("water", "soil"), "chemical", "mg/L", "US EPA 300.1"),
    _a("nitrate_n", "Nitrate NO3 as N", ("water", "soil", "sediment"), "chemical", "mg/L",
       "US EPA 300.1"),
    _a("nitrite_n", "Nitrite NO2 as N", ("water", "sediment"), "chemical", "mg/L",
       "US EPA 300.1"),
    _a("inorganic_n", "Inorganic nitrogen (NO3 + NO2) as N", ("water",), "chemical", "mg/L",
       "US EPA 300.1"),
    _a("phosphate", "Phosphate (PO4)", ("water", "soil", "sediment"), "chemical", "mg/L",
       "US EPA 300.1"),
    _a("sulphate", "Sulphate (SO4)", ("water",), "chemical", "mg/L", "US EPA 300.1"),
    _a("sulphide", "Sulphide (S)", ("water",), "chemical", "mg/L", "APHA 4500 S"),
    _a("sulphur", "Sulphur (S)", ("soil",), "chemical", "mg/kg", "APHA 4500-SO4-E"),
    _a("ammonia_n", "Ammonia, total as N", ("water", "soil", "sediment"), "chemical", "mg/L",
       "APHA 4500-NH3-G"),
    _a("ammonia_nh3", "Ammonia, total as NH3", ("water",), "chemical", "mg/L",
       "APHA 4500-NH3-G"),
    _a("tn", "Total nitrogen (TN) as N", ("water", "soil", "sediment"), "chemical", "mg/L",
       "APHA 4500-N"),
    _a("tkn", "Total Kjeldahl nitrogen (TKN) as N", ("water",), "chemical", "mg/L",
       "APHA 4500-N"),
    _a("phosphorus", "Total phosphorus (P)", ("water", "soil", "sediment"), "chemical", "mg/L",
       "SMWW 4500-P C"),
    _a("silicate", "Silicate (SiO2)", ("water",), "chemical", "mg/L", "APHA 4500-SiO2"),

    # --- metals ---------------------------------------------------------
    _a("al", "Aluminium (Al)", ("water", "soil"), "metals", "mg/L", "EPA 200.7"),
    _a("sb", "Antimony (Sb)", ("water", "soil"), "metals", "mg/L", "EPA 200.7"),
    _a("as", "Arsenic (As)", ("water", "soil", "sediment"), "metals", "mg/L", "EPA 200.7"),
    _a("ba", "Barium (Ba)", ("water", "soil", "sediment"), "metals", "mg/L", "EPA 200.7"),
    _a("be", "Beryllium (Be)", ("water", "soil"), "metals", "mg/L", "EPA 200.7"),
    _a("b", "Boron (B)", ("water", "soil"), "metals", "mg/L", "EPA 200.7"),
    _a("cd", "Cadmium (Cd)", ("water", "soil", "sediment"), "metals", "mg/L", "EPA 200.7"),
    _a("ca", "Calcium (Ca)", ("water", "soil"), "metals", "mg/L", "EPA 200.7"),
    _a("cr", "Chromium, total (Cr)", ("water", "soil", "sediment"), "metals", "mg/L",
       "EPA 200.7"),
    _a("cr6", "Chromium, hexavalent (Cr VI)", ("water", "soil", "sediment"), "metals", "mg/L",
       "EPA 200.7"),
    _a("mg", "Magnesium (Mg)", ("water", "soil"), "metals", "mg/L", "EPA 200.7"),
    _a("co", "Cobalt (Co)", ("water", "soil", "sediment"), "metals", "mg/L", "EPA 200.7"),
    _a("cu", "Copper (Cu)", ("water", "soil", "sediment"), "metals", "mg/L", "EPA 200.7"),
    _a("fe", "Iron (Fe)", ("water", "soil", "sediment"), "metals", "mg/L", "EPA 200.7"),
    _a("pb", "Lead (Pb)", ("water", "soil", "sediment"), "metals", "mg/L", "EPA 200.7"),
    _a("li", "Lithium (Li)", ("water",), "metals", "mg/L", "EPA 200.7"),
    _a("mn", "Manganese (Mn)", ("water", "soil"), "metals", "mg/L", "EPA 200.7"),
    _a("hg", "Mercury (Hg)", ("water", "soil", "sediment"), "metals", "mg/L", "EPA 200.7"),
    _a("mo", "Molybdenum (Mo)", ("water", "soil"), "metals", "mg/L", "EPA 200.7"),
    _a("ni", "Nickel (Ni)", ("water", "soil", "sediment"), "metals", "mg/L", "EPA 200.7"),
    _a("k", "Potassium (K)", ("water", "soil"), "metals", "mg/L", "EPA 200.7"),
    _a("se", "Selenium (Se)", ("water", "soil"), "metals", "mg/L", "EPA 200.7"),
    _a("ag", "Silver (Ag)", ("water", "soil"), "metals", "mg/L", "EPA 200.7"),
    _a("na", "Sodium (Na)", ("water",), "metals", "mg/L", "EPA 200.7"),
    _a("tl", "Thallium (Tl)", ("water", "soil"), "metals", "mg/L", "EPA 200.7"),
    _a("sn", "Tin (Sn)", ("water", "soil", "sediment"), "metals", "mg/L", "EPA 200.7"),
    _a("v", "Vanadium (V)", ("water", "soil"), "metals", "mg/L", "EPA 200.7"),
    _a("zn", "Zinc (Zn)", ("water", "soil", "sediment"), "metals", "mg/L", "EPA 200.7"),

    # --- organics -------------------------------------------------------
    _a("benzene", "Benzene", ("water", "soil", "sediment"), "btex", "mg/L", "EPA 5021A"),
    _a("ethylbenzene", "Ethylbenzene", ("water", "soil", "sediment"), "btex", "mg/L",
       "EPA 5021A"),
    _a("toluene", "Toluene", ("water", "soil", "sediment"), "btex", "mg/L", "EPA 5021A"),
    _a("xylene", "Xylenes", ("water", "soil", "sediment"), "btex", "mg/L", "EPA 5021A",
       ("Xylene",)),
    _a("total_vocs", "Total VOCs", ("sediment",), "organics", "mg/kg", "EPA 5021A"),
    _a("chlorinated_hc", "Chlorinated hydrocarbons", ("water",), "organics", "mg/L",
       "EPA 8081B"),
    _a("phenols", "Phenols", ("water", "soil"), "organics", "mg/L", "APHA 5530"),
    _a("fog", "Total oil and grease", ("water", "soil"), "organics", "mg/L", "APHA 5520 B",
       ("FOG",)),
    _a("toc", "Total organic carbon", ("water", "soil", "sediment"), "organics", "mg/L",
       "APHA 5310C", ("TOC",)),
    _a("organic_matter", "Total organic matter", ("water", "sediment"), "organics", "%",
       "ASTM D2974"),
    _a("tph", "Total petroleum hydrocarbons", ("water", "sediment"), "tph", "mg/L",
       "APHA 5520 F"),
    _a("tph_c6_c9", "TPH (C6-C9)", ("water",), "tph", "mg/L", "EPA 5021A"),
    _a("tph_c10_c30", "TPH (C10-C30)", ("water",), "tph", "mg/L", "EPA 8015D"),
    _a("f1", "F1: C6 to C10", ("soil",), "tph", "mg/kg", "EPA 5021A"),
    _a("f2", "F2: C10 to C16", ("soil",), "tph", "mg/kg", "EPA 8015D"),
    _a("f3", "F3: C16 to C34", ("soil",), "tph", "mg/kg", "ASTM D5442"),
    _a("f4", "F4: C34 to C50", ("soil",), "tph", "mg/kg", "ASTM D5442"),
    _a("pahs", "Polycyclic aromatic hydrocarbons (PAHs)", ("water", "sediment"), "pah",
       "mg/L", "EPA 610"),

    # --- microbiology ---------------------------------------------------
    _a("ecoli", "E. coli", ("water",), "microbiology", "CFU / 100 mL", "APHA SM9213D"),
    _a("enterococcus", "Enterococcus", ("water",), "microbiology", "CFU / 100 mL",
       "APHA 9230 B"),
    _a("intestinal_enterococci", "Intestinal enterococci", ("water",), "microbiology",
       "CFU / 100 mL", "Method 1106.1"),
    _a("hpc", "Heterotrophic plate count", ("water",), "microbiology", "CFU / mL", "EPA 9215"),
    _a("legionella", "Legionella", ("water",), "microbiology", "CFU / 100 mL",
       "EPA Method 1605"),
    _a("pseudomonas", "Pseudomonas", ("water",), "microbiology", "CFU / 100 mL", "APHA 9213 E"),
    _a("total_coliform", "Total coliform", ("water",), "microbiology", "CFU / 100 mL",
       "APHA 9222B"),

    # --- grain size -----------------------------------------------------
    _a("gravel", "Grain size — gravel", ("soil", "sediment"), "grain_size", "%",
       "Sieve analysis"),
    _a("sand", "Grain size — sand", ("soil", "sediment"), "grain_size", "%", "Sieve analysis"),
    _a("mud", "Grain size — mud", ("soil", "sediment"), "grain_size", "%", "Sieve analysis"),
)

ANALYTES_BY_KEY: Dict[str, Analyte] = {a.key: a for a in ANALYTES}

# Spellings that appear on BSA's own certificate templates and on laboratory
# sheets. Kept explicit rather than fuzzy-matched: a fuzzy match that picks
# total chromium when the sheet said hexavalent chromium is a wrong number
# printed with confidence.
EXTRA_ALIASES: Dict[str, Tuple[str, ...]] = {
    "cr": ("chromium cr", "chromium total cr", "chromium (total)", "total chromium"),
    "cr6": ("chromium cr (iv)", "chromium cr iv", "chromium (vi)", "hexavalent chromium"),
    "as": ("arsenic as", "arsenic (inorganic)"),
    "mn": ("manganase mn", "manganese mn"),
    "fe": ("iron fe",),
    "al": ("aluminum al", "aluminium al", "aluminum", "aluminium"),
    "ag": ("silver ag",),
    "sn": ("tin sn", "tin ti"),
    "pb": ("lead pb",),
    "hg": ("mercury hg",),
    "ni": ("nickel ni",),
    "cu": ("copper cu",),
    "zn": ("zinc zn",),
    "cd": ("cadmium cd",),
    "co": ("cobalt co",),
    "ba": ("barium ba",),
    "ca": ("calcium ca",),
    "mg": ("magnesium mg",),
    "k": ("potassium k",),
    "na": ("sodium na",),
    "se": ("selenium se",),
    "mo": ("molybdenum mo",),
    "li": ("lithium li",),
    "tl": ("thallium tl",),
    "v": ("vanadium v",),
    "b": ("boron b",),
    "be": ("beryllium be",),
    "sb": ("antimony sb",),
    "cyanide_free": ("cyanide (cn)", "cyanide cn", "cyanide free"),
    "sulphur": ("sulphur s", "sulfur s", "sulfur"),
    "sulphide": ("sulphide s", "sulfide"),
    "sulphate": ("sulphate so4", "sulfate so4", "sulfate"),
    "fluoride": ("fluoride f",),
    "chloride": ("chloride cl-", "chloride (cl)", "chloride cl"),
    "phosphate": ("phosphate po4",),
    "phosphorus": ("total phosphorus p", "phosphorus p"),
    "nitrate_n": ("nitrate no3 as n", "nitrate no3"),
    "nitrite_n": ("nitrite no2 as n",),
    "ammonia_n": ("ammonia nh3 as n", "ammonia nh3", "ammonia, total as n"),
    "toc": ("total organic carbon toc",),
    "fog": ("fats, oils , grease fog", "fats oils grease fog",
            "fat oil and grease (fog)", "fat, oil and grease"),
    "organic_matter": ("organic matter",),
    "tph": ("total tph", "total petroleum hydrocarbon", "tph"),
    "tph_c10_c30": ("tph (c10-30)", "tph c10-c30"),
    "ph": ("ph (in 0.01m cacl2)",),
    "do": ("dissolved oxygen (do)",),
    "cod": ("chemical oxygen demand (cod)",),
    "bod5": ("biological oxygen demand (bod5)", "biological oxygen demand (bod)"),
    "tds": ("total dissolved solids (tds)",),
    "tss": (),
    "gravel": ("grain size gravel", "gravel"),
    "sand": ("grain size sand", "sand"),
    "mud": ("grain size mud", "mud"),
}


def _norm(text: str) -> str:
    """Fold a written parameter name to a comparable key.

    Case, repeated whitespace and a trailing full stop are noise; nothing
    else is touched. Two different parameters never fold to the same string.
    """
    s = " ".join(str(text).split()).strip().rstrip(".").lower()
    return s.replace("\u2013", "-").replace("\u2014", "-")


_ALIAS_INDEX: Dict[str, str] = {}
for _an in ANALYTES:
    _ALIAS_INDEX[_norm(_an.name)] = _an.key
    _ALIAS_INDEX[_norm(_an.key)] = _an.key
    for _al in _an.aliases:
        _ALIAS_INDEX[_norm(_al)] = _an.key
for _key, _als in EXTRA_ALIASES.items():
    if _key not in ANALYTES_BY_KEY:
        continue
    for _al in _als:
        _ALIAS_INDEX.setdefault(_norm(_al), _key)


def resolve_analyte(text: str) -> Optional[Analyte]:
    """Map a name as written on a laboratory sheet to a library analyte.

    Returns None rather than a best guess. An unresolved name is reported
    with its result and no verdict; it is never silently matched to a
    different parameter.
    """
    if not text:
        return None
    return ANALYTES_BY_KEY.get(_ALIAS_INDEX.get(_norm(text), ""))


def analytes_for(media: str) -> List[Analyte]:
    return [a for a in ANALYTES if media in a.media]


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
_NO_CONTEXT = ("The context that selects this limit has not been recorded, "
               "so no limit applies and no compliance conclusion is drawn.")
_NO_ROW = ("This parameter has no limit in the regulation. The result is "
           "reported for information only.")
_NBL_REASON = ("The regulation gives this limit as the natural background "
               "level. No fixed figure applies until background has been "
               "established.")


def _soil_rows(analyte: str, depth: Optional[str]) -> List[SoilRow]:
    rows = [r for r in SOIL_LIMITS if r["analyte"] == analyte]
    if not rows:
        return []
    split = [r for r in rows if r["depth"]]
    if split:
        if depth not in DEPTHS:
            return []
        return [r for r in split if r["depth"] == depth]
    return rows


def soil_limit(analyte: str, particle_size: Optional[str],
               land_use: Optional[str], depth: Optional[str] = None) -> Limit:
    """The Appendix (1) soil limit for one analyte in one context.

    All three of particle size, land use and (for the hydrocarbon rows)
    depth must be recorded. Any of them missing returns an unassessable
    limit — Appendix (1) has five land-use columns and choosing the wrong
    one produces a compliance conclusion against the wrong standard.
    """
    rows = _soil_rows(analyte, depth)
    if not rows:
        known = any(r["analyte"] == analyte for r in SOIL_LIMITS)
        reason = _NO_CONTEXT if known else _NO_ROW
        return Limit(analyte=analyte, unit="", assessable=False, reason=reason,
                     source=SOIL_SOURCE)
    row = rows[0]
    unit = str(row["unit"])
    if particle_size not in PARTICLE_SIZES or land_use not in LAND_USES:
        return Limit(analyte=analyte, unit=unit, assessable=False,
                     reason=_NO_CONTEXT, source=SOIL_SOURCE)
    values = row["coarse"] if particle_size == "coarse" else row["soft"]
    value = values[LAND_USES.index(land_use)]  # type: ignore[index]
    if value is None:
        return Limit(analyte=analyte, unit=unit, assessable=False,
                     reason=_NO_ROW, source=SOIL_SOURCE,
                     note=row["note"])  # type: ignore[arg-type]
    return Limit(analyte=analyte, unit=unit, assessable=True,
                 direction=str(row["direction"]), value=float(value),
                 source=SOIL_SOURCE, note=row["note"])  # type: ignore[arg-type]


def water_ambient_limit(analyte: str, media: Optional[str]) -> Limit:
    """The Appendix (1) ambient water limit for one analyte in one class."""
    rows = [r for r in WATER_AMBIENT if r["analyte"] == analyte]
    if not rows:
        return Limit(analyte=analyte, unit="", assessable=False,
                     reason=_NO_ROW, source=WATER_AMBIENT_SOURCE)
    row = rows[0]
    unit = str(row["unit"])
    note = row["note"]  # type: ignore[assignment]
    if not row["assessable"]:
        return Limit(analyte=analyte, unit=unit, assessable=False,
                     reason=str(note), source=WATER_AMBIENT_SOURCE)
    if media not in WATER_MEDIA:
        return Limit(analyte=analyte, unit=unit, assessable=False,
                     reason=_NO_CONTEXT, source=WATER_AMBIENT_SOURCE, note=note)
    idx = WATER_MEDIA.index(media)
    direction = str(row["direction"])
    if direction == "range":
        band = row["ranges"][idx] if row["ranges"] else None  # type: ignore[index]
        if not band:
            return Limit(analyte=analyte, unit=unit, assessable=False,
                         reason=_NO_ROW, source=WATER_AMBIENT_SOURCE, note=note)
        return Limit(analyte=analyte, unit=unit, assessable=True,
                     direction="range", low=float(band[0]), high=float(band[1]),
                     source=WATER_AMBIENT_SOURCE, note=note)
    value = row["values"][idx]  # type: ignore[index]
    if value is None:
        return Limit(analyte=analyte, unit=unit, assessable=False,
                     reason=_NO_ROW, source=WATER_AMBIENT_SOURCE, note=note)
    if value == NBL:
        return Limit(analyte=analyte, unit=unit, assessable=False,
                     reason=_NBL_REASON, source=WATER_AMBIENT_SOURCE, note=note)
    return Limit(analyte=analyte, unit=unit, assessable=True,
                 direction=direction, value=float(value),  # type: ignore[arg-type]
                 source=WATER_AMBIENT_SOURCE, note=note)


def discharge_limit(analyte: str, destination: Optional[str],
                    single_sample: bool = True) -> Limit:
    """The Appendix (2) or (3) limit for treated wastewater.

    A single grab sample is judged against the bracketed maximum-for-any-
    sample figure only. Where the regulation states a 30-day or annual
    average and gives no single-sample maximum, one sample cannot establish
    compliance and no verdict is given.
    """
    rows = [r for r in DISCHARGE_LIMITS
            if r["analyte"] == analyte and r["destination"] == destination]
    if not rows:
        known = any(r["analyte"] == analyte for r in DISCHARGE_LIMITS)
        if destination not in DISCHARGE_DESTINATIONS:
            return Limit(analyte=analyte, unit="", assessable=False,
                         reason=_NO_CONTEXT)
        return Limit(analyte=analyte, unit="", assessable=False,
                     reason=_NO_CONTEXT if known else _NO_ROW)
    row = rows[0]
    unit = str(row["unit"])
    src = DISCHARGE_SOURCE.get(str(destination), "")
    note = row["note"]  # type: ignore[assignment]
    direction = str(row["direction"])
    if direction == "range":
        return Limit(analyte=analyte, unit=unit, assessable=True,
                     direction="range", low=row["low"], high=row["high"],  # type: ignore[arg-type]
                     source=src, note=note)
    if single_sample:
        smax = row["smax"]
        if smax is None:
            return Limit(
                analyte=analyte, unit=unit, assessable=False, source=src, note=note,
                reason=("The regulation states this limit as a "
                        f"{INTERVAL_LABELS[str(row['interval'])].lower()} and gives no "
                        "maximum for a single sample. One sample cannot "
                        "establish compliance."))
        if smax == NBL:
            return Limit(analyte=analyte, unit=unit, assessable=False,
                         reason=_NBL_REASON, source=src, note=note)
        return Limit(analyte=analyte, unit=unit, assessable=True,
                     direction=direction, value=float(smax),  # type: ignore[arg-type]
                     source=src, note=note)
    avg = row["avg"]
    if avg is None:
        return Limit(analyte=analyte, unit=unit, assessable=False,
                     reason=_NO_ROW, source=src, note=note)
    return Limit(analyte=analyte, unit=unit, assessable=True,
                 direction=direction, value=float(avg),  # type: ignore[arg-type]
                 source=src, note=note)


def soil_limit_row(analyte: str, particle_size: str,
                   depth: Optional[str] = None) -> Optional[Dict[str, object]]:
    """All five land-use values for one analyte, for the Appendix A table
    that shows what would have applied under a different land use."""
    rows = _soil_rows(analyte, depth)
    if not rows or particle_size not in PARTICLE_SIZES:
        return None
    row = rows[0]
    values = row["coarse"] if particle_size == "coarse" else row["soft"]
    return {
        "analyte": analyte,
        "unit": row["unit"],
        "values": dict(zip(LAND_USES, values)),  # type: ignore[arg-type]
        "source": SOIL_SOURCE,
    }


__all__ = [
    "LAND_USES", "LAND_USE_LABELS", "PARTICLE_SIZES", "PARTICLE_SIZE_LABELS",
    "DEPTHS", "DEPTH_LABELS", "WATER_MEDIA", "WATER_MEDIA_LABELS",
    "DISCHARGE_DESTINATIONS", "DISCHARGE_DESTINATION_LABELS",
    "INTERVALS", "INTERVAL_LABELS", "NBL", "Limit", "Analyte", "ANALYTES",
    "ANALYTES_BY_KEY", "resolve_analyte", "analytes_for",
    "SOIL_LIMITS", "WATER_AMBIENT", "DISCHARGE_LIMITS",
    "SOIL_SOURCE", "WATER_AMBIENT_SOURCE", "DISCHARGE_SOURCE",
    "soil_limit", "water_ambient_limit", "discharge_limit", "soil_limit_row",
]
