"""Mobile-lab (station) library and campaign attachments.

Stations
--------
Each mobile laboratory is saved once with its standard instrument set, then
loaded into a campaign with one click. The campaign keeps its own copy of the
rows, so editing a lab later never rewrites reports already issued.

Attachments
-----------
Field photos (Figure 2), calibration certificates (Appendix 3, each linked to
an instrument serial number), the environmental licence (Appendix 4), an
optional site-map override (Figure 1) and an optional cover photo. PDFs are
converted to images on upload so they can be placed in the DOCX.
"""
from __future__ import annotations

import io
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Response,
                     UploadFile, status)

import storage
from audit import audit
from auth import current_username
from db import db, to_mongo
from models import (ATTACHMENT_KINDS, Attachment, AttachmentUpdate, Station,
                    StationCreate, StationUpdate)

log = logging.getLogger(__name__)
router = APIRouter(tags=["stations", "attachments"])

MEDIA_DIR = os.environ.get("MEDIA_DIR", "/data/attachments")
MAX_MB = 25
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


# ---------------------------------------------------------------------------
# Mobile-lab library
# ---------------------------------------------------------------------------
@router.get("/stations", response_model=List[Station])
async def list_stations():
    docs = await db.stations.find({}, {"_id": 0}).sort("name", 1) \
        .to_list(length=200)
    return [Station(**d) for d in docs]


@router.post("/stations", response_model=Station,
             status_code=status.HTTP_201_CREATED)
async def create_station(payload: StationCreate,
                         user: str = Depends(current_username)):
    st = Station(**payload.model_dump())
    await db.stations.insert_one(to_mongo(st.model_dump()))
    await audit("station.create", "station", st.id, user, {"name": st.name})
    return st


@router.put("/stations/{station_id}", response_model=Station)
async def update_station(station_id: str, payload: StationUpdate,
                         user: str = Depends(current_username)):
    existing = await db.stations.find_one({"id": station_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Station not found")
    updates = payload.model_dump(exclude_unset=True)
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc)
        await db.stations.update_one({"id": station_id},
                                     {"$set": to_mongo(updates)})
        await audit("station.update", "station", station_id, user,
                    {"name": existing.get("name"),
                     "fields": list(updates.keys())})
    fresh = await db.stations.find_one({"id": station_id}, {"_id": 0})
    return Station(**fresh)


@router.delete("/stations/{station_id}", status_code=204)
async def delete_station(station_id: str,
                         user: str = Depends(current_username)) -> Response:
    res = await db.stations.delete_one({"id": station_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Station not found")
    await audit("station.delete", "station", station_id, user, {})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/campaigns/{campaign_id}/load-station/{station_id}")
async def load_station_into_campaign(campaign_id: str, station_id: str,
                                     user: str = Depends(current_username)):
    """Copy a mobile lab's instrument set into the campaign (editable there)."""
    st = await db.stations.find_one({"id": station_id}, {"_id": 0})
    if not st:
        raise HTTPException(status_code=404, detail="Station not found")
    camp = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await db.campaigns.update_one(
        {"id": campaign_id},
        {"$set": to_mongo({"station_id": station_id,
                           "instruments": st.get("instruments", []),
                           "updated_at": datetime.now(timezone.utc)})})
    await audit("campaign.load_station", "campaign", campaign_id, user,
                {"station": st.get("name"),
                 "instruments": len(st.get("instruments", []))})
    return {"station": st.get("name"),
            "instruments": st.get("instruments", [])}


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------
def _pdf_to_images(src: str, dest_dir: str) -> List[str]:
    """Render each PDF page to PNG so it can be embedded in the DOCX."""
    out: List[str] = []
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(src)
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=170)
            p = os.path.join(dest_dir, f"{uuid.uuid4().hex}_p{i + 1}.png")
            pix.save(p)
            out.append(p)
        doc.close()
        return out
    except Exception:  # noqa: BLE001
        log.warning("PyMuPDF unavailable/failed, trying pdftoppm", exc_info=True)
    try:
        import subprocess
        stem = os.path.join(dest_dir, uuid.uuid4().hex)
        subprocess.run(["pdftoppm", "-png", "-r", "170", src, stem],
                       check=True, capture_output=True, timeout=180)
        out = sorted(p for p in
                     (os.path.join(dest_dir, f) for f in os.listdir(dest_dir))
                     if p.startswith(stem) and p.endswith(".png"))
    except Exception:  # noqa: BLE001
        log.exception("PDF -> image conversion failed")
    return out


@router.get("/campaigns/{campaign_id}/attachments",
            response_model=List[Attachment])
async def list_attachments(campaign_id: str, kind: Optional[str] = None):
    q = {"campaign_id": campaign_id}
    if kind:
        q["kind"] = kind
    docs = await db.attachments.find(q, {"_id": 0}) \
        .sort([("kind", 1), ("order", 1), ("uploaded_at", 1)]) \
        .to_list(length=500)
    return [Attachment(**d) for d in docs]


@router.post("/campaigns/{campaign_id}/attachments",
             status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    campaign_id: str,
    kind: str = Form(...),
    caption: Optional[str] = Form(None),
    instrument_sn: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    user: str = Depends(current_username),
):
    if kind not in ATTACHMENT_KINDS:
        raise HTTPException(status_code=422,
                            detail=f"kind must be one of {ATTACHMENT_KINDS}")
    if not await db.campaigns.find_one({"id": campaign_id}, {"_id": 0}):
        raise HTTPException(status_code=404, detail="Campaign not found")

    dest_dir = os.path.join(MEDIA_DIR, campaign_id, kind)
    os.makedirs(dest_dir, exist_ok=True)
    start_order = await db.attachments.count_documents(
        {"campaign_id": campaign_id, "kind": kind})
    created: List[Attachment] = []

    for n, up in enumerate(files):
        raw = await up.read()
        if len(raw) > MAX_MB * 1024 * 1024:
            raise HTTPException(status_code=413,
                                detail=f"{up.filename} exceeds {MAX_MB} MB")
        ext = os.path.splitext(up.filename or "")[1].lower()
        stored: List[tuple] = []

        if ext == ".pdf":
            tmp = os.path.join(dest_dir, f"{uuid.uuid4().hex}.pdf")
            with open(tmp, "wb") as fh:
                fh.write(raw)
            pages = _pdf_to_images(tmp, dest_dir)
            os.remove(tmp)
            if not pages:
                raise HTTPException(
                    status_code=422,
                    detail=(f"Could not read {up.filename}. Please upload the "
                            f"certificate as an image (JPG/PNG) instead."))
            for i, p in enumerate(pages):
                label = (f"{caption} — page {i + 1}"
                         if caption and len(pages) > 1 else caption)
                stored.append((os.path.basename(p), p, label))
        elif ext in IMAGE_EXT:
            p = os.path.join(dest_dir, f"{uuid.uuid4().hex}{ext}")
            with open(p, "wb") as fh:
                fh.write(raw)
            stored.append((up.filename, p, caption))
        else:
            raise HTTPException(
                status_code=422,
                detail=f"{up.filename}: only images and PDF are accepted")

        for k, (fname, path, cap) in enumerate(stored):
            meta = storage.store_report(path, campaign_id,
                                        f"attachments/{kind}/"
                                        f"{os.path.basename(path)}")
            att = Attachment(
                campaign_id=campaign_id, kind=kind, filename=fname or "file",
                path=path, caption=cap, instrument_sn=instrument_sn,
                order=start_order + n + k,
                size_bytes=os.path.getsize(path),
                storage=meta["storage"], s3_key=meta["s3_key"],
                uploaded_by=user)
            await db.attachments.insert_one(to_mongo(att.model_dump()))
            created.append(att)

    await audit("attachment.upload", "campaign", campaign_id, user,
                {"kind": kind, "files": len(created)})
    return created


@router.patch("/attachments/{attachment_id}", response_model=Attachment)
async def update_attachment(attachment_id: str, payload: AttachmentUpdate,
                            user: str = Depends(current_username)):
    doc = await db.attachments.find_one({"id": attachment_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Attachment not found")
    updates = payload.model_dump(exclude_unset=True)
    if updates:
        await db.attachments.update_one({"id": attachment_id},
                                        {"$set": to_mongo(updates)})
    fresh = await db.attachments.find_one({"id": attachment_id}, {"_id": 0})
    return Attachment(**fresh)


@router.delete("/attachments/{attachment_id}", status_code=204)
async def delete_attachment(attachment_id: str,
                            user: str = Depends(current_username)) -> Response:
    doc = await db.attachments.find_one({"id": attachment_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Attachment not found")
    await db.attachments.delete_one({"id": attachment_id})
    try:
        if doc.get("path") and os.path.exists(doc["path"]):
            os.remove(doc["path"])
    except OSError:
        pass
    await audit("attachment.delete", "campaign", doc["campaign_id"], user,
                {"kind": doc.get("kind"), "filename": doc.get("filename")})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/attachments/{attachment_id}/file")
async def get_attachment_file(attachment_id: str):
    from fastapi.responses import FileResponse
    doc = await db.attachments.find_one({"id": attachment_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = storage.fetch_report(doc)
    if not path:
        raise HTTPException(status_code=410, detail="File no longer available")
    return FileResponse(path, filename=doc["filename"])
