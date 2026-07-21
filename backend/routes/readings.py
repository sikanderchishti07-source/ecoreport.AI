"""Readings CRUD + CSV/XLSX/XLS ingest endpoints."""
from __future__ import annotations

import io
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status

from db import db, to_mongo
from models import (
    ALL_MEASUREMENT_FIELDS,
    Reading,
    ReadingFlagUpdate,
    UploadLog,
    UploadResult,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["readings"])


# ---------------------------------------------------------------------------
# Column alias map: accept common variants and normalize to schema field names.
# Covers both my "clean schema" naming and real-world vendor exports
# (e.g. Teledyne AAQMS: AMBTEMP, BARPRESS, RELHUM, WDR, WSP, OZONE, NOX).
# ---------------------------------------------------------------------------
_COLUMN_ALIASES = {
    # Timestamp
    "timestamp": "timestamp", "time": "timestamp", "datetime": "timestamp",
    "date/time": "timestamp", "date_time": "timestamp", "date": "timestamp",
    # SO2
    "so2": "SO2", "so\u2082": "SO2",
    # NO / NO2 / NOx
    "no": "NO",
    "no2": "NO2", "no\u2082": "NO2",
    "nox": "NOx", "no_x": "NOx",
    # CO
    "co": "CO",
    # H2S
    "h2s": "H2S", "h\u2082s": "H2S",
    # O3 (aka OZONE)
    "o3": "O3", "o\u2083": "O3", "ozone": "O3",
    # PM
    "pm10": "PM10", "pm\u2081\u2080": "PM10",
    "pm25": "PM25", "pm2.5": "PM25", "pm_2_5": "PM25", "pm\u2082.\u2085": "PM25",
    # Temperature
    "temp": "Temp", "temperature": "Temp",
    "ambtemp": "Temp", "amb_temp": "Temp", "ambient temp": "Temp",
    "ambient temperature": "Temp",
    # Relative humidity
    "rh": "RH", "humidity": "RH", "relative humidity": "RH",
    "relhum": "RH", "rel_hum": "RH",
    # Barometric pressure
    "pressure": "Pressure", "barometric pressure": "Pressure",
    "barpress": "Pressure", "bar_press": "Pressure", "bp": "Pressure",
    # Wind
    "windspeed": "WindSpeed", "wind speed": "WindSpeed",
    "ws": "WindSpeed", "wsp": "WindSpeed",
    "winddirection": "WindDirection", "wind direction": "WindDirection",
    "wd": "WindDirection", "wdr": "WindDirection",
}


# Columns commonly found in vendor exports that are NOT part of the AAQ schema
# (analyzer flow rates, aux met, calibration diagnostics). Track separately so
# users can see what was dropped, but don't error on their presence.
_KNOWN_IGNORED_TOKENS = {
    "coflow", "so2flow", "no2flow", "noflow", "noxflow", "h2sflow", "o3flow",
    "pmflow", "pmcoarse", "solarrad", "rainfall", "aqms",
}


def _norm_key(col) -> str:
    return re.sub(r"\s+", " ", str(col).strip().lower())


def _looks_like_generic_headers(cols: list[str]) -> bool:
    """Heuristic: header row like ['Unnamed: 0', 'AQMS', 'AQMS.1', ...]
    means the real headers are one row below."""
    normalized = [_norm_key(c) for c in cols]
    unnamed_hits = sum(1 for c in normalized if c.startswith("unnamed"))
    # Repeated prefix pattern: same base word with .N suffixes
    base_repeats: dict[str, int] = {}
    for c in normalized:
        base = re.sub(r"\.\d+$", "", c)
        base_repeats[base] = base_repeats.get(base, 0) + 1
    max_repeat = max(base_repeats.values(), default=0)
    return unnamed_hits >= 2 or max_repeat >= 4


def _row_looks_like_parameter_names(row: pd.Series) -> bool:
    """True when this row's cells match known schema aliases (>= 3 hits)."""
    hits = 0
    for v in row:
        if pd.isna(v):
            continue
        key = _norm_key(v)
        if key in _COLUMN_ALIASES or key in _KNOWN_IGNORED_TOKENS:
            hits += 1
    return hits >= 3


def _row_looks_like_sublabel(row: pd.Series) -> bool:
    """True when only one non-NaN cell equals 'date' / 'time' / similar."""
    non_null = [v for v in row if not pd.isna(v)]
    if len(non_null) != 1:
        return False
    return _norm_key(non_null[0]) in {"date", "time", "timestamp", "datetime"}


def _promote_header_if_needed(df: pd.DataFrame) -> pd.DataFrame:
    """Vendor exports often merge the top row across all columns (yielding
    'Unnamed: 0' / 'AQMS' repeated headers). In that case the real headers
    are on the first data row, and the second data row is a 'Date' sub-label.
    Detect and rewrite so downstream code sees a normal DataFrame."""
    if not _looks_like_generic_headers(list(df.columns)):
        return df
    if df.empty:
        return df
    first = df.iloc[0]
    if not _row_looks_like_parameter_names(first):
        return df

    new_cols = [str(v).strip() if not pd.isna(v) else f"col_{i}"
                for i, v in enumerate(first)]
    df2 = df.iloc[1:].copy()
    df2.columns = new_cols

    # If the next row is a "Date" sub-label, drop it as well.
    if not df2.empty and _row_looks_like_sublabel(df2.iloc[0]):
        df2 = df2.iloc[1:]

    df2.reset_index(drop=True, inplace=True)
    return df2


def _normalize_columns(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str], List[str]]:
    """Rename columns to schema names. Returns (df, recognized, ignored)."""
    rename_map: dict = {}
    recognized: List[str] = []
    ignored: List[str] = []
    for col in df.columns:
        key = _norm_key(col)
        target = _COLUMN_ALIASES.get(key)
        if target:
            rename_map[col] = target
            recognized.append(target)
        else:
            ignored.append(str(col))
    df2 = df.rename(columns=rename_map)
    # De-dup recognized in case aliases collide (e.g. Temp + AMBTEMP both map)
    recognized = list(dict.fromkeys(recognized))
    return df2, recognized, ignored


def _detect_timestamp_by_content(df: pd.DataFrame) -> Optional[str]:
    """If no column matched the 'timestamp' alias, find a column whose values
    parse as datetimes (vendor exports often leave the timestamp column's
    header cell blank, so we pick it up by content)."""
    for col in df.columns:
        sample = df[col].dropna().head(5)
        if sample.empty:
            continue
        try:
            parsed = pd.to_datetime(sample, errors="raise")
            # Reject numeric-looking columns that pandas may still coerce.
            if pd.api.types.is_numeric_dtype(sample):
                continue
            if parsed.notna().all():
                return str(col)
        except (ValueError, TypeError):
            continue
    return None


async def _load_dataframe(file: UploadFile) -> tuple[pd.DataFrame, str]:
    filename = (file.filename or "").lower()
    contents = await file.read()
    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(contents))
        file_type = "csv"
    elif filename.endswith(".xlsx"):
        df = pd.read_excel(io.BytesIO(contents), engine="openpyxl")
        file_type = "xlsx"
    elif filename.endswith(".xls"):
        df = pd.read_excel(io.BytesIO(contents), engine="xlrd")
        file_type = "xls"
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload a .csv, .xlsx, or .xls file.",
        )
    return df, file_type


@router.post(
    "/campaigns/{campaign_id}/upload",
    response_model=UploadResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_readings(campaign_id: str, file: UploadFile = File(...)) -> UploadResult:
    campaign = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    df, file_type = await _load_dataframe(file)
    df = _promote_header_if_needed(df)
    df, recognized, ignored = _normalize_columns(df)

    # Fallback: if 'timestamp' is missing but one of the unrecognized columns
    # holds datetime-looking values, adopt it as the timestamp column.
    if "timestamp" not in df.columns:
        ts_col = _detect_timestamp_by_content(df)
        if ts_col is not None:
            df = df.rename(columns={ts_col: "timestamp"})
            if str(ts_col) in ignored:
                ignored.remove(str(ts_col))
            recognized = ["timestamp"] + recognized

    if "timestamp" not in df.columns:
        raise HTTPException(
            status_code=400,
            detail=(
                "Missing required column 'timestamp' (ISO-8601, hourly cadence). "
                f"Detected columns: {list(df.columns)[:20]}"
            ),
        )

    ingested: List[Reading] = []
    errors: List[str] = []
    skipped = 0
    to_insert = []

    for idx, row in df.iterrows():
        try:
            ts_raw = row.get("timestamp")
            if pd.isna(ts_raw):
                skipped += 1
                errors.append(f"Row {idx + 2}: empty timestamp — skipped.")
                continue
            ts = pd.to_datetime(ts_raw, utc=False, errors="raise")
            if ts.tzinfo is None:
                ts = ts.tz_localize(timezone.utc)
            reading_kwargs = {"campaign_id": campaign_id, "timestamp": ts.to_pydatetime()}
            for field in ALL_MEASUREMENT_FIELDS:
                if field in df.columns:
                    val = row[field]
                    if pd.isna(val):
                        reading_kwargs[field] = None
                    else:
                        try:
                            reading_kwargs[field] = float(val)
                        except (TypeError, ValueError):
                            reading_kwargs[field] = None
            reading = Reading(**reading_kwargs)
            ingested.append(reading)
            to_insert.append(to_mongo(reading.model_dump()))
        except Exception as exc:  # noqa: BLE001 — surface parse errors to user
            skipped += 1
            errors.append(f"Row {idx + 2}: {exc}")

    if to_insert:
        await db.readings.insert_many(to_insert)
        await db.campaigns.update_one(
            {"id": campaign_id, "status": "draft"},
            {"$set": {"status": "ingested"}},
        )

    upload_log = UploadLog(
        campaign_id=campaign_id,
        filename=file.filename or "unknown",
        file_type=file_type,
        rows_ingested=len(to_insert),
        rows_skipped=skipped,
        errors=errors[:20],
        recognized_columns=recognized,
        ignored_columns=ignored,
    )
    await db.upload_logs.insert_one(to_mongo(upload_log.model_dump()))

    return UploadResult(upload_log=upload_log, preview=ingested[:10])


@router.get("/campaigns/{campaign_id}/readings", response_model=List[Reading])
async def list_readings(
    campaign_id: str,
    limit: int = Query(500, le=5000, ge=1),
    offset: int = Query(0, ge=0),
    valid_only: Optional[bool] = None,
) -> List[Reading]:
    query: dict = {"campaign_id": campaign_id}
    if valid_only is True:
        query["valid"] = True
    elif valid_only is False:
        query["valid"] = False
    cursor = (
        db.readings.find(query, {"_id": 0})
        .sort("timestamp", 1)
        .skip(offset)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    return [Reading(**d) for d in docs]


@router.get("/campaigns/{campaign_id}/uploads", response_model=List[UploadLog])
async def list_upload_logs(campaign_id: str) -> List[UploadLog]:
    cursor = db.upload_logs.find({"campaign_id": campaign_id}, {"_id": 0}).sort(
        "uploaded_at", -1
    )
    docs = await cursor.to_list(length=200)
    return [UploadLog(**d) for d in docs]


@router.patch("/readings/{reading_id}", response_model=Reading)
async def flag_reading(reading_id: str, payload: ReadingFlagUpdate) -> Reading:
    existing = await db.readings.find_one({"id": reading_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Reading not found")
    updates = {
        "valid": payload.valid,
        "invalidation_reason": payload.invalidation_reason if not payload.valid else None,
    }
    await db.readings.update_one({"id": reading_id}, {"$set": updates})
    fresh = await db.readings.find_one({"id": reading_id}, {"_id": 0})
    return Reading(**fresh)


@router.delete(
    "/campaigns/{campaign_id}/readings",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def clear_readings(campaign_id: str) -> Response:
    await db.readings.delete_many({"campaign_id": campaign_id})
    await db.campaigns.update_one(
        {"id": campaign_id}, {"$set": {"status": "draft"}}
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
