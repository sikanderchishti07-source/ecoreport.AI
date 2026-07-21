"""Readings CRUD + CSV/XLSX ingest endpoints."""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import List, Optional

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


# Alias map: accept common column-name variants and normalize.
_COLUMN_ALIASES = {
    "timestamp": "timestamp", "time": "timestamp", "datetime": "timestamp",
    "date/time": "timestamp", "date_time": "timestamp",
    "so2": "SO2", "so\u2082": "SO2",
    "no": "NO",
    "no2": "NO2", "no\u2082": "NO2",
    "nox": "NOx",
    "co": "CO",
    "h2s": "H2S", "h\u2082s": "H2S",
    "o3": "O3", "o\u2083": "O3",
    "pm10": "PM10", "pm\u2081\u2080": "PM10",
    "pm25": "PM25", "pm2.5": "PM25", "pm\u2082.\u2085": "PM25", "pm_2_5": "PM25",
    "temp": "Temp", "temperature": "Temp",
    "rh": "RH", "humidity": "RH", "relative humidity": "RH",
    "pressure": "Pressure", "barometric pressure": "Pressure",
    "windspeed": "WindSpeed", "wind speed": "WindSpeed", "ws": "WindSpeed",
    "winddirection": "WindDirection", "wind direction": "WindDirection", "wd": "WindDirection",
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {}
    for col in df.columns:
        key = str(col).strip().lower()
        target = _COLUMN_ALIASES.get(key)
        if target:
            rename_map[col] = target
    return df.rename(columns=rename_map)


async def _load_dataframe(file: UploadFile) -> tuple[pd.DataFrame, str]:
    filename = (file.filename or "").lower()
    contents = await file.read()
    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(contents))
        file_type = "csv"
    elif filename.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(contents))
        file_type = "xlsx"
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload a .csv or .xlsx file.",
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
    df = _normalize_columns(df)

    if "timestamp" not in df.columns:
        raise HTTPException(
            status_code=400,
            detail="Missing required column 'timestamp' (ISO-8601, hourly cadence).",
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
            ts = pd.to_datetime(ts_raw, utc=False)
            if ts.tzinfo is None:
                ts = ts.tz_localize(timezone.utc)
            reading_kwargs = {"campaign_id": campaign_id, "timestamp": ts.to_pydatetime()}
            for field in ALL_MEASUREMENT_FIELDS:
                if field in df.columns:
                    val = row[field]
                    if pd.isna(val):
                        reading_kwargs[field] = None
                    else:
                        reading_kwargs[field] = float(val)
            reading = Reading(**reading_kwargs)
            ingested.append(reading)
            to_insert.append(to_mongo(reading.model_dump()))
        except Exception as exc:  # noqa: BLE001 — surface parse errors to user
            skipped += 1
            errors.append(f"Row {idx + 2}: {exc}")

    if to_insert:
        await db.readings.insert_many(to_insert)
        # Bump campaign status to "ingested" on first successful ingest.
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
        errors=errors[:20],  # cap payload
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
