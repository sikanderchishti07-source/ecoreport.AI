"""NCEC pollutant limits — read-only, seeded on startup."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter

from db import db
from models import PollutantLimit

router = APIRouter(prefix="/limits", tags=["limits"])


_POLLUTANT_ORDER = ["SO2", "CO", "O3", "H2S", "NO2", "PM10", "PM25"]
_PERIOD_ORDER = [
    "1 Hour",
    "8 Hour (rolling)",
    "24 Hour",
    "1 Year",
]


@router.get("", response_model=List[PollutantLimit])
async def list_limits() -> List[PollutantLimit]:
    docs = await db.pollutant_limits.find({}, {"_id": 0}).to_list(length=200)

    def _sort_key(d: dict) -> tuple:
        p_idx = _POLLUTANT_ORDER.index(d["pollutant"]) if d["pollutant"] in _POLLUTANT_ORDER else 99
        a_idx = _PERIOD_ORDER.index(d["averaging_period"]) if d["averaging_period"] in _PERIOD_ORDER else 99
        return p_idx, a_idx

    docs.sort(key=_sort_key)
    return [PollutantLimit(**d) for d in docs]
