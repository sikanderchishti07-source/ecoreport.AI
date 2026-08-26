"""Phase 7 — report file storage: local disk plus optional S3-compatible cloud.

Configured entirely by environment variables in backend/.env:

  STORAGE_BACKEND=local            (default — files stay on the server disk)
  STORAGE_BACKEND=s3               (upload every report to an S3 bucket too)

For s3 also set:
  S3_BUCKET=my-bucket
  AWS_ACCESS_KEY_ID=...
  AWS_SECRET_ACCESS_KEY=...
  S3_REGION=me-south-1             (optional)
  S3_ENDPOINT_URL=https://...      (optional — set for Backblaze B2, Supabase
                                    Storage, MinIO, DigitalOcean Spaces, or any
                                    other S3-compatible provider)

The local file is always written first (it is also the render output), then
mirrored to the bucket when s3 is enabled — so downloads survive server
redeploys/wipes. Downloads are streamed back through the API, which keeps all
access behind login.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from typing import Optional

log = logging.getLogger(__name__)

BACKEND = os.environ.get("STORAGE_BACKEND", "local").strip().lower()
S3_BUCKET = os.environ.get("S3_BUCKET", "")

_s3_client = None


def s3_enabled() -> bool:
    return BACKEND == "s3" and bool(S3_BUCKET)


def _s3():
    global _s3_client
    if _s3_client is None:
        import boto3
        kwargs = {}
        if os.environ.get("S3_REGION"):
            kwargs["region_name"] = os.environ["S3_REGION"]
        if os.environ.get("S3_ENDPOINT_URL"):
            kwargs["endpoint_url"] = os.environ["S3_ENDPOINT_URL"]
        _s3_client = boto3.client("s3", **kwargs)
    return _s3_client


def store_report(local_path: str, campaign_id: str, filename: str) -> dict:
    """Called after a report is rendered. Returns storage metadata for the
    report_logs entry. Cloud upload failures are logged but never block the
    report from being delivered."""
    meta = {"storage": "local", "s3_key": None}
    if not s3_enabled():
        return meta
    key = f"reports/{campaign_id}/{filename}"
    try:
        _s3().upload_file(local_path, S3_BUCKET, key)
        meta.update({"storage": "s3", "s3_key": key})
        log.info("report mirrored to s3://%s/%s", S3_BUCKET, key)
    except Exception:  # noqa: BLE001
        log.exception("S3 upload failed — report kept on local disk only")
    return meta


def fetch_report(report_doc: dict) -> Optional[str]:
    """Return a readable local path for a stored report, downloading from the
    bucket if the local copy is gone. None if the file is unrecoverable."""
    path = report_doc.get("path")
    if path and os.path.exists(path):
        return path
    key = report_doc.get("s3_key")
    if key and s3_enabled():
        try:
            tmp = os.path.join(tempfile.gettempdir(), "ecoreport_cache")
            os.makedirs(tmp, exist_ok=True)
            local = os.path.join(tmp, os.path.basename(key))
            _s3().download_file(S3_BUCKET, key, local)
            return local
        except Exception:  # noqa: BLE001
            log.exception("S3 download failed for %s", key)
    return None


def delete_report(report_doc: dict) -> dict:
    """Remove a stored report's file, from disk and from the bucket.

    Returns what was actually removed rather than raising. A file that has
    already gone — a redeploy wiped local disk, or the bucket object was
    removed by hand — is not an error worth blocking a deletion over: the
    record is being deleted precisely because it is no longer wanted, and
    refusing because the file is already absent would leave the archive
    holding a row pointing at nothing.
    """
    out = {"local": False, "s3": False, "errors": []}

    path = report_doc.get("path")
    if path and os.path.exists(path):
        try:
            os.remove(path)
            out["local"] = True
        except OSError as exc:
            out["errors"].append(f"local: {exc}")

    key = report_doc.get("s3_key")
    if key and s3_enabled():
        try:
            _s3().delete_object(Bucket=S3_BUCKET, Key=key)
            out["s3"] = True
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"s3: {exc}")

    # The on-screen reader caches a rendered page image per report. Left
    # behind, those outlive the report they belong to and quietly fill the
    # disk with pages of documents nobody can open any more.
    cache = os.path.join(
        os.environ.get("REPORT_DIR",
                       os.path.join(tempfile.gettempdir(),
                                    "ecoreport_reports")),
        "_pages", str(report_doc.get("id", "")))
    if report_doc.get("id") and os.path.isdir(cache):
        try:
            shutil.rmtree(cache)
        except OSError as exc:
            out["errors"].append(f"cache: {exc}")

    return out
