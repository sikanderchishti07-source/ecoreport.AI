"""Phase 3 endpoint — generate and download the AAQ report DOCX."""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from audit import audit
from auth import current_user, current_username
from db import db, to_mongo
import storage
from models import Campaign, PollutantLimit, Reading
from report.generate import convert_to_pdf, generate_report
from report_filename import report_filename

log = logging.getLogger(__name__)
router = APIRouter(tags=["report"])

REPORT_DIR = os.environ.get("REPORT_DIR", os.path.join(tempfile.gettempdir(), "ecoreport_reports"))

# On-screen reader --------------------------------------------------------
# Field operators read the whole report in the browser but never receive the
# file. Streaming the PDF would defeat that: Chrome's own viewer puts a
# download button on the page. So each page is rasterised and served as an
# image — there is no document in the browser to save, only the page being
# looked at. Rendered once and cached; a report is immutable, so a cached
# page never goes stale.
PAGES_DIR = os.path.join(REPORT_DIR, "_pages")
VIEW_DPI = 110          # comfortable on screen, ~120 KB a page


def _cache_dir(report_id: str) -> str:
    d = os.path.join(PAGES_DIR, report_id)
    os.makedirs(d, exist_ok=True)
    return d


def _viewable_pdf(doc: dict) -> str:
    """A PDF of this report version, converting the DOCX once if needed."""
    src = storage.fetch_report(doc)
    if not src:
        raise HTTPException(
            status_code=410,
            detail=("This version's file is no longer on the server. "
                    "Generate the report again to create a new version."))
    if (doc.get("format") or "").lower() == "pdf":
        return src
    cache = _cache_dir(doc["id"])
    pdf = os.path.join(cache, "view.pdf")
    if os.path.exists(pdf) and os.path.getsize(pdf) > 0:
        return pdf
    work = os.path.join(cache, os.path.basename(src))
    if not os.path.exists(work):
        shutil.copy(src, work)
    produced = convert_to_pdf(work, cache)
    if produced != pdf:
        shutil.move(produced, pdf)
    try:
        os.remove(work)
    except OSError:
        pass
    return pdf


def _page_image(doc: dict, page: int) -> str:
    cache = _cache_dir(doc["id"])
    img = os.path.join(cache, "p%04d.jpg" % page)
    if os.path.exists(img) and os.path.getsize(img) > 0:
        return img
    pdf_path = _viewable_pdf(doc)
    try:
        import fitz  # PyMuPDF — already required for certificate rendering
        with fitz.open(pdf_path) as pdf:
            if page < 1 or page > pdf.page_count:
                raise HTTPException(status_code=404, detail="No such page")
            pdf[page - 1].get_pixmap(dpi=VIEW_DPI).save(img, jpg_quality=80)
        return img
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        log.warning("PyMuPDF page render failed — trying pdftoppm",
                    exc_info=True)
    # Same fallback the certificate renderer uses, for hosts where PyMuPDF
    # cannot be imported.
    import subprocess
    stem = os.path.join(cache, "tmp_p%04d" % page)
    subprocess.run(["pdftoppm", "-jpeg", "-r", str(VIEW_DPI),
                    "-f", str(page), "-l", str(page), "-singlefile",
                    pdf_path, stem],
                   check=True, capture_output=True, timeout=180)
    produced = stem + ".jpg"
    if not os.path.exists(produced):
        raise HTTPException(status_code=404, detail="No such page")
    shutil.move(produced, img)
    return img


def _render_all(doc: dict, total: int) -> None:
    """Render every page once, in the background, right after the first
    request. Rendering on demand made scrolling stutter: each page waited on
    its own round trip. One pass costs a few seconds and every page after it
    is served from disk."""
    try:
        for n in range(1, total + 1):
            _page_image(doc, n)
    except Exception:  # noqa: BLE001
        log.warning("background page render stopped early", exc_info=True)


def _page_geometry(doc: dict) -> tuple:
    """Page count and the aspect ratio of the first page, so the reader can
    lay out placeholders at the right height before any image arrives."""
    pdf_path = _viewable_pdf(doc)
    try:
        import fitz
        with fitz.open(pdf_path) as pdf:
            r = pdf[0].rect if pdf.page_count else None
            return (pdf.page_count,
                    float(r.width) if r else 595.0,
                    float(r.height) if r else 842.0)
    except Exception:  # noqa: BLE001
        log.warning("PyMuPDF unavailable — using pdfinfo", exc_info=True)
    import re as _re
    import subprocess
    out = subprocess.run(["pdfinfo", pdf_path], capture_output=True,
                         timeout=60).stdout.decode("utf-8", "replace")
    m = _re.search(r"Pages:\s+(\d+)", out)
    if not m:
        raise HTTPException(status_code=500,
                            detail="Could not read the report for viewing")
    size = _re.search(r"Page size:\s+([\d.]+) x ([\d.]+)", out)
    w, h = (float(size.group(1)), float(size.group(2))) if size else (595.0, 842.0)
    return int(m.group(1)), w, h


async def _report_or_404(report_id: str) -> dict:
    doc = await db.report_logs.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Report version not found")
    return doc


@router.get("/reports/{report_id}/page-count")
async def report_page_count(report_id: str, background: BackgroundTasks):
    """Open the report for reading. Open to every signed-in account — reading
    is not downloading.

    The first call on a DOCX version converts it with LibreOffice, which is
    the slow part and happens once. Every page is then rendered in the
    background so the reader scrolls without waiting on each one.
    """
    doc = await _report_or_404(report_id)
    pages, width, height = await run_in_threadpool(_page_geometry, doc)
    background.add_task(run_in_threadpool, _render_all, doc, pages)
    return {"report_id": report_id, "pages": pages,
            "page_width": width, "page_height": height,
            "filename": doc.get("filename")}


@router.get("/reports/{report_id}/page/{page}")
async def report_page(report_id: str, page: int):
    doc = await _report_or_404(report_id)
    img = await run_in_threadpool(_page_image, doc, page)
    return FileResponse(img, media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=86400"})




def _require_window(campaign) -> None:
    """Refuse to build a report against a campaign with no window.

    The window is normally set by the first upload, so this is reached only
    where a campaign was created and never given data, or where the operator
    kept a window they had not yet filled in. Refusing here with a plain
    sentence is better than the alternative: every calculation downstream
    assumes two datetimes, and without them the failure is a TypeError deep
    in the engine that says nothing about what to do.
    """
    if not campaign.monitoring_start or not campaign.monitoring_end:
        raise HTTPException(
            status_code=400,
            detail=("This campaign has no monitoring window. Upload the data "
                    "file and the window is read from it, or set the start "
                    "and end dates on the campaign."))


async def resolve_client_name(campaign) -> None:
    """Print the client's recorded legal name where the campaign is linked.

    A campaign carries the client as typed, and most in the archive predate
    the client records entirely. Where a record exists the report prints its
    legal name, so "SAJCO", "saico private" and "SAJCO QIDDIYAH" all issue as
    one company; where none exists the typed text is used exactly as before.

    Resolved here at generation, not written back to the campaign. A report
    reissued after a client's registered name changes then carries the new
    name, and the campaign remains a record of what was typed at the time.
    """
    client_id = getattr(campaign, "client_id", None)
    if not client_id:
        return
    doc = await db.clients.find_one({"id": client_id},
                                    {"_id": 0, "legal_name": 1})
    if doc and doc.get("legal_name"):
        campaign.client = doc["legal_name"]


@router.post("/campaigns/{campaign_id}/report")
async def create_report(campaign_id: str, lang: str = "en",
                        format: str = "docx",
                        x_user: str = Depends(current_username),
                        user: dict = Depends(current_user)):
    if lang not in ("en", "ar", "bilingual"):
        raise HTTPException(status_code=422,
                            detail="lang must be en, ar, or bilingual")
    if format not in ("docx", "pdf"):
        raise HTTPException(status_code=422,
                            detail="format must be docx or pdf")
    campaign_doc = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not campaign_doc:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign = Campaign(**campaign_doc)
    await resolve_client_name(campaign)
    _require_window(campaign)
    # After resolution this is the recorded legal name where the campaign is
    # linked to a client, and the typed text where it is not, so the saved
    # file is named the same way the report itself is.
    resolved_client = campaign.client

    # The number is allocated here, at the first report, and not when the
    # campaign was created: the date inside it is the issue date, and a
    # campaign that never produces a report should never consume a number.
    # Both report types pass through this point, so both are numbered.
    from report_numbers import ensure_report_number
    await ensure_report_number(campaign, campaign_id)

    # Noise campaigns take their own generator; everything downstream —
    # versioning, storage, the review workflow, the on-screen reader — is
    # shared because it operates on the produced file, not on how it was
    # made.
    if getattr(campaign, "campaign_type", "air") == "noise":
        return await _create_noise_report(campaign, campaign_id, lang,
                                          format, x_user, user)

    reading_docs = (
        await db.readings.find({"campaign_id": campaign_id}, {"_id": 0})
        .sort("timestamp", 1).to_list(length=100000)
    )
    if not reading_docs:
        raise HTTPException(status_code=400, detail="No readings ingested for this campaign")
    readings: List[Reading] = [Reading(**d) for d in reading_docs]

    limit_docs = await db.pollutant_limits.find({}, {"_id": 0}).to_list(length=200)
    limits: List[PollutantLimit] = [PollutantLimit(**d) for d in limit_docs]

    # Guard: a report with zero readings inside the monitoring window would be
    # an empty shell of N/R tables and blank charts. Fail early with the exact
    # mismatch so the user can fix the campaign dates or re-upload the data.
    from calc import _as_utc
    w_start, w_end = _as_utc(campaign.monitoring_start), _as_utc(campaign.monitoring_end)
    in_window = sum(1 for r in readings if w_start <= _as_utc(r.timestamp) < w_end)
    if in_window == 0:
        d_min = min(_as_utc(r.timestamp) for r in readings)
        d_max = max(_as_utc(r.timestamp) for r in readings)
        fmt = "%d %b %Y %H:%M"
        raise HTTPException(
            status_code=400,
            detail=(f"No readings fall inside this campaign's monitoring window. "
                    f"Your uploaded data covers {d_min.strftime(fmt)} to "
                    f"{d_max.strftime(fmt)} (UTC), but the campaign window is "
                    f"{w_start.strftime(fmt)} to {w_end.strftime(fmt)}. "
                    f"Edit the campaign's monitoring start/end dates to match "
                    f"the data (or re-upload the correct file), then generate "
                    f"again."))
    total_hours = max(int((w_end - w_start).total_seconds() // 3600), 1)
    if in_window < 0.05 * total_hours:
        log.warning("report window covers only %s readings of %s window hours",
                    in_window, total_hours)

    # Version number: sequential per campaign across all languages/formats
    version = await db.report_logs.count_documents(
        {"campaign_id": campaign_id}) + 1
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    # Two names. The stored file keeps its unique form so a redeploy or a
    # second generation in the same second cannot overwrite an archived
    # report; `download_name` is what the browser is told to save it as.
    fname = f"AAQ_Report_{campaign_id[:8]}_v{version:03d}_{lang}_{ts}.docx"
    download_name = report_filename(campaign, kind="air", version=version,
                                    lang=lang, fmt="docx",
                                    client_name=resolved_client)
    out_path = os.path.join(REPORT_DIR, campaign_id, fname)

    # Attachments: field photos (Figure 2), certificates (Appendix 3),
    # licence (Appendix 4), operator site-map override (Figure 1).
    atts = await db.attachments.find({"campaign_id": campaign_id}, {"_id": 0}) \
        .sort([("order", 1), ("uploaded_at", 1)]).to_list(length=500)
    by_kind: dict = {}
    for a in atts:
        by_kind.setdefault(a["kind"], []).append(a)

    site_photos = [a["path"] for a in by_kind.get("site_photo", [])
                   if os.path.exists(a.get("path", ""))]
    licence = [a["path"] for a in by_kind.get("license", [])
               if os.path.exists(a.get("path", ""))]
    if not licence:
        # The environmental licence belongs to the company, not the job, so
        # it is held once in the library and used by every report unless the
        # campaign carries its own.
        company = await db.attachments.find(
            {"kind": "license", "campaign_id": "", "station_id": None,
             "source_id": None}, {"_id": 0}) \
            .sort([("order", 1), ("uploaded_at", 1)]).to_list(length=50)
        licence = [a["path"] for a in company
                   if os.path.exists(a.get("path", ""))]
    cover = next((a["path"] for a in by_kind.get("cover_photo", [])
                  if os.path.exists(a.get("path", ""))), None)

    def _as_dict(i):
        return i if isinstance(i, dict) else i.model_dump()
    sn_map = {_as_dict(i).get("sn"): _as_dict(i)
              for i in (campaign.instruments or [])}
    cal_items = []
    for a in by_kind.get("calibration", []):
        if not os.path.exists(a.get("path", "")):
            continue
        instr = sn_map.get(a.get("instrument_sn"))
        if instr:
            title = (f"Calibration certificate — {instr.get('technique','')} "
                     f"({instr.get('parameter','')}), S/N {instr.get('sn','')}")
        else:
            title = a.get("caption") or "Calibration certificate"
        cal_items.append({"title": title.strip(" —"), "path": a["path"]})

    # Calibration certificates: the lab's own records are used unless the
    # campaign supplied its own, and only those valid for this survey window.
    from report.certificates import select as select_certs, to_rows as cert_to_rows
    station_certs = []
    if campaign.station_id:
        station_certs = await db.attachments.find(
            {"station_id": campaign.station_id, "kind": "calibration"},
            {"_id": 0}).to_list(length=200)
    chosen_certs, cert_warnings = select_certs(
        [a for a in by_kind.get("calibration", []) if a.get("cert_number")],
        station_certs, w_start, w_end)
    for msg in cert_warnings:
        log.warning("campaign %s: %s", campaign_id, msg)
    cert_rows = cert_to_rows(chosen_certs, campaign.instruments)

    # Scans follow the same selection, so Appendix 3's table and its images
    # always describe the same certificates.
    for c in chosen_certs:
        if not os.path.exists(c.get("path", "")):
            continue
        if any(item["path"] == c["path"] for item in cal_items):
            continue
        instr = sn_map.get(c.get("instrument_sn"))
        if instr:
            title = (f"Calibration certificate — {instr.get('technique','')} "
                     f"({instr.get('parameter','')}), S/N {instr.get('sn','')}")
        else:
            title = (f"Calibration certificate "
                     f"{c.get('cert_number', '')}").strip()
        cal_items.append({"title": title.strip(" —"), "path": c["path"]})

    # Figure 1 — satellite site map (operator upload wins over the auto map)
    site_map = next((a["path"] for a in by_kind.get("site_map", [])
                     if os.path.exists(a.get("path", ""))), None)
    if not site_map:
        try:
            from report.sitemap import fetch_site_map
            # Blocking HTTP call — keep it off the event loop.
            site_map = await run_in_threadpool(
                fetch_site_map,
                campaign.latitude, campaign.longitude,
                os.path.join(REPORT_DIR, campaign_id, "site_map.png"))
        except Exception:  # noqa: BLE001
            log.warning("automatic site map unavailable", exc_info=True)
            site_map = None

    try:
        # Rendering and LibreOffice conversion are blocking and CPU-bound.
        # Run them off the event loop or the whole API stops responding for
        # the duration of the build.
        await run_in_threadpool(
            generate_report, campaign, readings, limits, out_path, lang=lang,
            site_map_path=site_map,
            site_photo_paths=site_photos,
            cover_photo_path=cover,
            calibration_items=cal_items,
            cert_rows=cert_rows,
            license_image_paths=licence)
        if format == "pdf":
            out_path = await run_in_threadpool(convert_to_pdf, out_path)
            fname = os.path.basename(out_path)
            # The extension changes with the file, so the download name has
            # to follow it or a PDF is offered under a .docx name.
            download_name = download_name.rsplit(".", 1)[0] + ".pdf"
    except Exception as exc:  # noqa: BLE001
        log.exception("report generation failed")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {exc}")

    # S3 mirror is a network upload — also blocking.
    storage_meta = await run_in_threadpool(
        storage.store_report, out_path, campaign_id, fname)
    report_id = str(uuid.uuid4())
    await db.report_logs.insert_one(to_mongo({
        "id": report_id,
        "storage": storage_meta["storage"],
        "s3_key": storage_meta["s3_key"],
        "campaign_id": campaign_id,
        "project_name": campaign.project_name,
        "version": version,
        "filename": fname,
        # The readable name. Kept on the record so the archive and the
        # client portal offer the same name the generator did, without
        # having to rebuild it from a campaign that may since have changed.
        "download_name": download_name,
        "path": out_path,
        "lang": lang,
        "format": format,
        "generated_by": x_user,
        "generated_at": datetime.now(timezone.utc),
        "readings_count": len(readings),
        "size_bytes": os.path.getsize(out_path),
    }))
    await audit("report.generate", "report", report_id, x_user,
                {"campaign_id": campaign_id, "version": version,
                 "lang": lang, "format": format, "filename": fname})

    # Field operators generate and read the report on screen, but the file
    # itself only leaves the system through an admin. This endpoint returns
    # the bytes, so for a non-admin it returns the version record instead —
    # the report is still built, stored and logged, and the reviewer
    # downloads it from the versions list. See routes/review.py.
    if user.get("role") != "admin":
        return JSONResponse({
            "download": False,
            "report_id": report_id,
            "filename": fname,
            "download_name": download_name,
            "version": version,
            "format": format,
            "lang": lang,
            "size_bytes": os.path.getsize(out_path),
            "detail": ("Report generated. Downloads are handled by the "
                       "reviewing engineer — use Submit for review when the "
                       "campaign is ready."),
        })

    media = ("application/pdf" if format == "pdf" else
             "application/vnd.openxmlformats-officedocument"
             ".wordprocessingml.document")
    return FileResponse(out_path, media_type=media,
                        filename=download_name)


@router.get("/campaigns/{campaign_id}/reports")
async def list_reports(campaign_id: str):
    docs = await db.report_logs.find(
        {"campaign_id": campaign_id}, {"_id": 0}
    ).sort("generated_at", -1).to_list(length=100)
    return docs


@router.get("/campaigns/{campaign_id}/report-preview")
async def preview_report(campaign_id: str):
    """Everything the report will say, without building the document.

    Lets the operator check the figures, the compliance verdicts and the
    readiness warnings in the browser before spending a minute on generation.
    """
    campaign_doc = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not campaign_doc:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign = Campaign(**campaign_doc)
    await resolve_client_name(campaign)
    _require_window(campaign)
    resolved_client = campaign.client

    if getattr(campaign, "campaign_type", "air") == "noise":
        # The noise summary endpoint already says everything a pre-flight
        # check needs; the panel renders it directly.
        from routes.noise import noise_summary as _ns
        data = await _ns(campaign_id)
        data["campaign_type"] = "noise"
        return data

    reading_docs = await db.readings.find(
        {"campaign_id": campaign_id}, {"_id": 0}).sort("timestamp", 1) \
        .to_list(length=None)
    readings = [Reading(**d) for d in reading_docs]
    if not readings:
        raise HTTPException(status_code=400,
                            detail="No readings uploaded for this campaign")

    limit_docs = await db.pollutant_limits.find({}, {"_id": 0}).to_list(length=200)
    limits = [PollutantLimit(**d) for d in limit_docs]

    from calc import _as_utc, build_campaign_summary
    w_start, w_end = _as_utc(campaign.monitoring_start), _as_utc(campaign.monitoring_end)
    in_window = sum(1 for r in readings if w_start <= _as_utc(r.timestamp) < w_end)

    blockers, warnings = [], []
    if in_window == 0:
        d_min = min(_as_utc(r.timestamp) for r in readings)
        d_max = max(_as_utc(r.timestamp) for r in readings)
        fmt = "%d %b %Y %H:%M"
        blockers.append(
            f"No readings fall inside the monitoring window. Your data covers "
            f"{d_min.strftime(fmt)} to {d_max.strftime(fmt)}, but the window is "
            f"{w_start.strftime(fmt)} to {w_end.strftime(fmt)}.")
        return {"ready": False, "blockers": blockers, "warnings": [],
                "sections": [], "pollutants": [], "campaign": None,
                "headline": None}

    summary = build_campaign_summary(campaign, readings, limits)

    if (summary.overall_hourly_capture_pct or 0) < 75:
        warnings.append(
            f"Overall data capture is {summary.overall_hourly_capture_pct:.1f}%, "
            f"below the 75% requirement. Affected parameters will print as "
            f"N/R* (not reportable).")
    not_reportable = [p.pollutant for p in summary.pollutants
                      if not p.is_supporting and (p.hourly_capture_pct or 0) < 75]
    if not_reportable:
        warnings.append("Not reportable at hourly resolution: "
                        + ", ".join(not_reportable))

    atts = await db.attachments.find({"campaign_id": campaign_id},
                                     {"_id": 0}).to_list(length=500)
    kinds = {}
    for a in atts:
        kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
    if not kinds.get("site_photo"):
        warnings.append("No field photos uploaded — Figure 2 will be empty.")
    if not kinds.get("calibration"):
        warnings.append("No calibration certificates uploaded — Appendix 3 "
                        "will be empty.")
    if not campaign.instruments:
        warnings.append("No instruments set — Table 4 will fall back to the "
                        "default list. Load a mobile lab on the Instruments tab.")
    if not campaign.report_number:
        warnings.append("Report number is blank.")

    def pol_row(p):
        return {
            "pollutant": p.pollutant,
            "supporting": p.is_supporting,
            "capture_pct": round(p.hourly_capture_pct or 0, 1),
            "max": p.hourly_max, "min": p.hourly_min, "mean": p.hourly_mean,
            "mdl": p.mdl_ugm3, "below_mdl": p.below_mdl_count,
            "periods": [{
                "period": e.averaging_period,
                "limit": e.limit_ugm3,
                "capture_pct": round(e.capture_pct, 1),
                "exceedances": e.exceedance_count,
                "verdict": e.verdict,
            } for e in p.period_evaluations],
        }

    exceedances = sum(e.exceedance_count for p in summary.pollutants
                      for e in p.period_evaluations)
    sections = [
        {"title": "Executive summary", "figures": 1, "tables": 1},
        {"title": "Monitoring and data collection", "figures": 2, "tables": 3},
        {"title": "Ambient air quality standards", "figures": 0, "tables": 1},
        {"title": "Calibration and maintenance", "figures": 0, "tables": 0},
        {"title": "Results and discussion", "figures": 16, "tables": 10},
        {"title": "Conclusions", "figures": 0, "tables": 0},
        {"title": "Appendices", "figures": kinds.get("calibration", 0), "tables": 0},
    ]

    return {
        "ready": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "campaign": {
            "project_name": campaign.project_name,
            "client": campaign.client,
            "site_name": campaign.site_name,
            "report_number": campaign.report_number,
            "revision": campaign.revision,
            "window": f"{w_start.strftime('%d %b %Y %H:%M')} — "
                      f"{w_end.strftime('%d %b %Y %H:%M')}",
        },
        "headline": {
            "monitoring_hours": summary.monitoring_hours,
            "capture_pct": round(summary.overall_hourly_capture_pct or 0, 1),
            "readings_in_window": in_window,
            "exceedances": exceedances,
            "prevailing_wind": summary.wind_rose.prevailing_direction,
            "instruments": len(campaign.instruments or []),
            "attachments": kinds,
        },
        "pollutants": [pol_row(p) for p in summary.pollutants],
        "sections": sections,
    }


# ---------------------------------------------------------------------------
# Noise report generation
# ---------------------------------------------------------------------------
async def _create_noise_report(campaign, campaign_id: str, lang: str,
                               format: str, x_user: str, user: dict):
    from noise_calc import assess, build_noise_summary
    from report.noise_charts import generate_noise_charts
    from report.noise_generate import generate_noise_report

    if lang != "en":
        raise HTTPException(
            status_code=422,
            detail="Noise reports are English-only in this version — "
                   "Arabic follows once the wording is approved.")

    readings = await db.noise_readings.find(
        {"campaign_id": campaign_id}, {"_id": 0}).sort("timestamp", 1) \
        .to_list(length=None)
    if not readings:
        raise HTTPException(status_code=400,
                            detail="No noise readings uploaded for this "
                                   "campaign")

    summary = build_noise_summary(readings, campaign.monitoring_start,
                                  campaign.monitoring_end,
                                  campaign.day_start_hour,
                                  campaign.day_end_hour)
    # Article (7): construction sites are judged against the zone around them
    # plus the Table (4) correction. Without both facts assess() returns no
    # verdict and the report says so, rather than judging against a guess.
    verdicts = assess(summary, campaign.noise_category,
                      getattr(campaign, "construction_base_category", None),
                      getattr(campaign, "construction_hours_per_day", None))

    out_dir = os.path.join(REPORT_DIR, campaign_id)
    os.makedirs(out_dir, exist_ok=True)
    version = 1 + await db.report_logs.count_documents(
        {"campaign_id": campaign_id})
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = (f"Noise_Report_{campaign_id[:8]}_v{version:03d}_"
             f"{lang}_{stamp}.docx")
    # The campaign object arrives with its client already resolved by
    # create_report, so the name is taken from it directly. Referring to that
    # function's local would be a NameError the first time a noise report was
    # generated.
    download_name = report_filename(campaign, kind="noise", version=version,
                                    lang=lang, fmt="docx",
                                    client_name=campaign.client)
    out_path = os.path.join(out_dir, fname)
    charts_dir = os.path.join(out_dir, "charts")

    figs = await run_in_threadpool(
        generate_noise_charts, summary, readings,
        campaign.noise_category, charts_dir)

    # Attachments, collected exactly as the air report collects them —
    # same kinds, same certificate selection — so a noise campaign behaves
    # the way the operator already expects. The first version looked for a
    # "field_photo" kind that nothing writes and ignored cover photographs
    # entirely, which is why a selected cover never appeared.
    atts = await db.attachments.find({"campaign_id": campaign_id},
                                     {"_id": 0}) \
        .sort([("order", 1), ("uploaded_at", 1)]).to_list(length=500)
    by_kind: dict = {}
    for a in atts:
        by_kind.setdefault(a["kind"], []).append(a)

    site_photos = [a["path"] for a in by_kind.get("site_photo", [])
                   if os.path.exists(a.get("path", ""))]
    licence = [a["path"] for a in by_kind.get("license", [])
               if os.path.exists(a.get("path", ""))]
    cover = next((a["path"] for a in by_kind.get("cover_photo", [])
                  if os.path.exists(a.get("path", ""))), None)

    # Photographs of the equipment, held against the library record so every
    # campaign using that meter gets them without re-uploading.
    equipment_photos: list = []
    if campaign.station_id:
        eq = await db.attachments.find(
            {"station_id": campaign.station_id, "kind": "equipment_photo"},
            {"_id": 0}).sort([("order", 1), ("uploaded_at", 1)]) \
            .to_list(length=20)
        equipment_photos = [a["path"] for a in eq
                            if os.path.exists(a.get("path", ""))]

    cal_items = []
    for a in by_kind.get("calibration", []):
        if os.path.exists(a.get("path", "")):
            cal_items.append({
                "title": a.get("caption") or "Calibration certificate",
                "path": a["path"]})

    # The lab's own certificates are used unless the campaign supplied its
    # own, and only those valid for this survey window — the same selector
    # the air report uses, so Appendix B fills itself with no extra work.
    try:
        from report.certificates import select as select_certs
        station_certs = []
        if campaign.station_id:
            station_certs = await db.attachments.find(
                {"station_id": campaign.station_id, "kind": "calibration"},
                {"_id": 0}).to_list(length=200)
        chosen_certs, cert_warnings = select_certs(
            [a for a in by_kind.get("calibration", [])
             if a.get("cert_number")],
            station_certs, campaign.monitoring_start,
            campaign.monitoring_end)
        for msg in cert_warnings:
            log.warning("campaign %s: %s", campaign_id, msg)
        for c in chosen_certs:
            if not os.path.exists(c.get("path", "")):
                continue
            if any(item["path"] == c["path"] for item in cal_items):
                continue
            cal_items.append({
                "title": (f"Calibration certificate "
                          f"{c.get('cert_number', '')}").strip(),
                "path": c["path"]})
    except Exception:  # noqa: BLE001
        log.warning("certificate selection unavailable for the noise report",
                    exc_info=True)

    # Figure 1 — an operator-uploaded map wins over the generated one.
    site_map = next((a["path"] for a in by_kind.get("site_map", [])
                     if os.path.exists(a.get("path", ""))), None)
    if not site_map:
        try:
            from report.sitemap import fetch_site_map
            # The marker defaults to AAQMS — the air monitoring station —
            # which is wrong on a noise report. The location is N1, the same
            # site ID used in the results tables.
            site_map = await run_in_threadpool(
                fetch_site_map, campaign.latitude, campaign.longitude,
                os.path.join(out_dir, "site_map.png"), label="N1")
        except Exception:  # noqa: BLE001
            log.warning("site map unavailable for noise report",
                        exc_info=True)

    try:
        await run_in_threadpool(
            generate_noise_report, campaign, summary, verdicts, figs,
            out_path, site_map, site_photos, cover, equipment_photos,
            cal_items, licence, charts_dir)
        from report.fields import build_indexes, populate_field_caches
        await run_in_threadpool(populate_field_caches, out_path)
        await run_in_threadpool(build_indexes, out_path, convert_to_pdf)
        if format == "pdf":
            out_path = await run_in_threadpool(convert_to_pdf, out_path)
            fname = os.path.basename(out_path)
            # The extension changes with the file, so the download name has
            # to follow it or a PDF is offered under a .docx name.
            download_name = download_name.rsplit(".", 1)[0] + ".pdf"
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("noise report generation failed")
        raise HTTPException(status_code=500,
                            detail=f"Report generation failed: {exc}")

    storage_meta = await run_in_threadpool(
        storage.store_report, out_path, campaign_id, fname)
    report_id = str(uuid.uuid4())
    await db.report_logs.insert_one(to_mongo({
        "id": report_id,
        "storage": storage_meta["storage"],
        "s3_key": storage_meta["s3_key"],
        "campaign_id": campaign_id,
        "project_name": campaign.project_name,
        "version": version,
        "filename": fname,
        # The readable name. Kept on the record so the archive and the
        # client portal offer the same name the generator did, without
        # having to rebuild it from a campaign that may since have changed.
        "download_name": download_name,
        "path": out_path,
        "lang": lang,
        "format": format,
        "generated_by": x_user,
        "generated_at": datetime.now(timezone.utc),
        "readings_count": len(readings),
        "size_bytes": os.path.getsize(out_path),
    }))
    await audit("report.generate", "report", report_id, x_user,
                {"campaign_id": campaign_id, "version": version,
                 "lang": lang, "format": format, "filename": fname,
                 "type": "noise"})

    if user.get("role") != "admin":
        return JSONResponse({
            "download": False, "report_id": report_id, "filename": fname,
            "download_name": download_name,
            "version": version, "format": format, "lang": lang,
            "size_bytes": os.path.getsize(out_path),
            "detail": ("Report generated. Downloads are handled by the "
                       "reviewing engineer — use Submit for review when "
                       "the campaign is ready.")})
    media = ("application/pdf" if format == "pdf" else
             "application/vnd.openxmlformats-officedocument"
             ".wordprocessingml.document")
    return FileResponse(out_path, media_type=media,
                        filename=download_name)
