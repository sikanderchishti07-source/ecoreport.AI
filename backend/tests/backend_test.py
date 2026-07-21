"""EcoReport AI — Phase 1 backend regression tests."""
import io
import os
import uuid
from datetime import datetime, timedelta

import openpyxl
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback: read frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def s():
    return requests.Session()


# ---------- basics ----------
def test_root(s):
    r = s.get(f"{API}/")
    assert r.status_code == 200
    j = r.json()
    assert j.get("service") == "EcoReport AI"
    assert j.get("status") == "ok"


def test_health(s):
    r = s.get(f"{API}/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---------- limits ----------
def test_limits_seeded_14_and_idempotent(s):
    r1 = s.get(f"{API}/limits")
    assert r1.status_code == 200
    d1 = r1.json()
    assert len(d1) == 14
    # Check specific limits
    by_key = {(x["pollutant"], x["averaging_period"]): x for x in d1}
    assert by_key[("SO2", "1 Hour")]["limit_ugm3"] == 441
    assert by_key[("SO2", "24 Hour")]["limit_ugm3"] == 217
    assert by_key[("SO2", "1 Year")]["limit_ugm3"] == 65
    assert by_key[("CO", "1 Hour")]["limit_ugm3"] == 40000
    assert by_key[("CO", "8 Hour (rolling)")]["limit_ugm3"] == 10000
    assert by_key[("O3", "8 Hour (rolling)")]["limit_ugm3"] == 157
    assert by_key[("H2S", "1 Hour")]["limit_ugm3"] == 14
    assert by_key[("H2S", "24 Hour")]["limit_ugm3"] == 4
    assert by_key[("NO2", "1 Hour")]["limit_ugm3"] == 200
    assert by_key[("NO2", "1 Year")]["limit_ugm3"] == 100
    assert by_key[("PM10", "24 Hour")]["limit_ugm3"] == 340
    assert by_key[("PM10", "1 Year")]["limit_ugm3"] == 50
    assert by_key[("PM25", "24 Hour")]["limit_ugm3"] == 35
    assert by_key[("PM25", "1 Year")]["limit_ugm3"] == 15
    # Idempotency
    r2 = s.get(f"{API}/limits")
    assert len(r2.json()) == 14


# ---------- campaign CRUD ----------
def _campaign_payload(name="TEST_Alpha"):
    return {
        "project_name": name,
        "client": "TEST_ACME",
        "site_name": "TEST_Yard",
        "latitude": 24.5,
        "longitude": 46.7,
        "monitoring_start": "2025-04-08T08:00:00",
        "monitoring_end": "2025-04-09T07:00:00",
    }


@pytest.fixture
def campaign(s):
    r = s.post(f"{API}/campaigns", json=_campaign_payload(f"TEST_{uuid.uuid4().hex[:6]}"))
    assert r.status_code == 201, r.text
    c = r.json()
    yield c
    s.delete(f"{API}/campaigns/{c['id']}")


def test_campaign_full_lifecycle(s):
    payload = _campaign_payload(f"TEST_LC_{uuid.uuid4().hex[:6]}")
    r = s.post(f"{API}/campaigns", json=payload)
    assert r.status_code == 201
    c = r.json()
    assert c["status"] == "draft"
    assert c["reading_count"] == 0
    assert uuid.UUID(c["id"])
    # Default wind bins
    bins = c["wind_rose_bins"]
    assert len(bins) == 3
    assert bins[0]["label"] == "Calm" and bins[0]["min"] == 0.0 and bins[0]["max"] == 2.10
    assert bins[1]["label"] == "2.10-3.60"
    assert bins[2]["label"] in ("\u22653.60", "≥3.60")
    assert bins[2]["max"] is None
    # No _id leak
    assert "_id" not in c

    # LIST
    rl = s.get(f"{API}/campaigns")
    assert rl.status_code == 200
    assert any(x["id"] == c["id"] for x in rl.json())

    # GET
    rg = s.get(f"{API}/campaigns/{c['id']}")
    assert rg.status_code == 200
    assert rg.json()["id"] == c["id"]

    # PUT partial
    new_bins = [{"label": "A", "min": 0, "max": 1.5}, {"label": "B", "min": 1.5, "max": None}]
    rp = s.put(f"{API}/campaigns/{c['id']}", json={"report_number": "RPT-42", "wind_rose_bins": new_bins})
    assert rp.status_code == 200
    upd = rp.json()
    assert upd["report_number"] == "RPT-42"
    assert len(upd["wind_rose_bins"]) == 2
    assert upd["project_name"] == payload["project_name"]  # untouched

    # DELETE
    rd = s.delete(f"{API}/campaigns/{c['id']}")
    assert rd.status_code == 204
    rg2 = s.get(f"{API}/campaigns/{c['id']}")
    assert rg2.status_code == 404


# ---------- upload CSV ----------
def _make_csv(n=5, bad_ts=False, empty_ts=False):
    header = "timestamp,SO2,NO,NO2,NOx,CO,H2S,O3,PM10,PM25,Temp,RH,Pressure,WindSpeed,WindDirection\n"
    rows = []
    base = datetime(2025, 4, 8, 8)
    for i in range(n):
        ts = (base + timedelta(hours=i)).isoformat()
        rows.append(f"{ts},10,5,20,25,300,2,50,40,20,25,45,1013,3.2,180")
    if empty_ts:
        rows.append(",10,5,20,25,300,2,50,40,20,25,45,1013,3.2,180")
    if bad_ts:
        rows.append("not-a-date,10,5,20,25,300,2,50,40,20,25,45,1013,3.2,180")
    return (header + "\n".join(rows)).encode()


def test_upload_csv(s, campaign):
    csv_bytes = _make_csv(5)
    files = {"file": ("data.csv", csv_bytes, "text/csv")}
    r = s.post(f"{API}/campaigns/{campaign['id']}/upload", files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["upload_log"]["rows_ingested"] == 5
    assert body["upload_log"]["rows_skipped"] == 0
    assert body["upload_log"]["file_type"] == "csv"
    assert body["upload_log"]["errors"] == []
    assert len(body["preview"]) == 5

    # readings sorted asc
    rr = s.get(f"{API}/campaigns/{campaign['id']}/readings")
    assert rr.status_code == 200
    rd = rr.json()
    assert len(rd) == 5
    ts_list = [x["timestamp"] for x in rd]
    assert ts_list == sorted(ts_list)

    # status ingested
    cg = s.get(f"{API}/campaigns/{campaign['id']}").json()
    assert cg["status"] == "ingested"
    assert cg["reading_count"] == 5


def test_upload_xlsx(s, campaign):
    wb = openpyxl.Workbook()
    ws = wb.active
    cols = ["timestamp","SO2","NO","NO2","NOx","CO","H2S","O3","PM10","PM25","Temp","RH","Pressure","WindSpeed","WindDirection"]
    ws.append(cols)
    base = datetime(2025, 4, 8, 8)
    for i in range(3):
        ws.append([(base + timedelta(hours=i)).isoformat(), 10,5,20,25,300,2,50,40,20,25,45,1013,3.2,180])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    files = {"file": ("data.xlsx", buf.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = s.post(f"{API}/campaigns/{campaign['id']}/upload", files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["upload_log"]["rows_ingested"] == 3
    assert body["upload_log"]["file_type"] == "xlsx"


def test_upload_bad_rows(s, campaign):
    csv_bytes = _make_csv(2, bad_ts=True, empty_ts=True)
    files = {"file": ("bad.csv", csv_bytes, "text/csv")}
    r = s.post(f"{API}/campaigns/{campaign['id']}/upload", files=files)
    assert r.status_code == 201
    body = r.json()
    assert body["upload_log"]["rows_ingested"] == 2
    assert body["upload_log"]["rows_skipped"] == 2
    assert len(body["upload_log"]["errors"]) == 2
    # row numbers referenced
    assert any("Row " in e for e in body["upload_log"]["errors"])


def test_upload_unsupported_type(s, campaign):
    files = {"file": ("data.txt", b"foo", "text/plain")}
    r = s.post(f"{API}/campaigns/{campaign['id']}/upload", files=files)
    assert r.status_code == 400


def test_upload_missing_timestamp(s, campaign):
    csv = b"SO2,NO\n10,5\n"
    files = {"file": ("nots.csv", csv, "text/csv")}
    r = s.post(f"{API}/campaigns/{campaign['id']}/upload", files=files)
    assert r.status_code == 400
    assert "timestamp" in r.json()["detail"].lower()


def test_upload_column_aliases(s, campaign):
    csv = (
        "Timestamp,PM2.5,Wind Speed,Relative Humidity,Barometric Pressure\n"
        "2025-04-08T08:00:00,20,3.2,45,1013\n"
        "2025-04-08T09:00:00,21,3.3,46,1014\n"
    ).encode()
    files = {"file": ("alias.csv", csv, "text/csv")}
    r = s.post(f"{API}/campaigns/{campaign['id']}/upload", files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["upload_log"]["rows_ingested"] == 2
    rd = s.get(f"{API}/campaigns/{campaign['id']}/readings").json()
    assert rd[0]["PM25"] == 20
    assert rd[0]["WindSpeed"] == 3.2
    assert rd[0]["RH"] == 45
    assert rd[0]["Pressure"] == 1013


def test_reading_flag_toggle(s, campaign):
    # ingest 3 rows first
    files = {"file": ("d.csv", _make_csv(3), "text/csv")}
    s.post(f"{API}/campaigns/{campaign['id']}/upload", files=files)
    readings = s.get(f"{API}/campaigns/{campaign['id']}/readings").json()
    rid = readings[0]["id"]

    r = s.patch(f"{API}/readings/{rid}", json={"valid": False, "invalidation_reason": "sensor calibration drift"})
    assert r.status_code == 200
    assert r.json()["valid"] is False
    assert r.json()["invalidation_reason"] == "sensor calibration drift"

    invalid_only = s.get(f"{API}/campaigns/{campaign['id']}/readings", params={"valid_only": "false"}).json()
    assert len(invalid_only) == 1
    assert invalid_only[0]["id"] == rid

    r2 = s.patch(f"{API}/readings/{rid}", json={"valid": True})
    assert r2.status_code == 200
    assert r2.json()["valid"] is True
    assert r2.json()["invalidation_reason"] is None


def test_clear_readings_resets_status(s, campaign):
    s.post(f"{API}/campaigns/{campaign['id']}/upload", files={"file": ("d.csv", _make_csv(2), "text/csv")})
    assert s.get(f"{API}/campaigns/{campaign['id']}").json()["status"] == "ingested"
    r = s.delete(f"{API}/campaigns/{campaign['id']}/readings")
    assert r.status_code == 204
    cg = s.get(f"{API}/campaigns/{campaign['id']}").json()
    assert cg["status"] == "draft"
    assert cg["reading_count"] == 0


def test_delete_campaign_cascade(s):
    payload = _campaign_payload(f"TEST_CASC_{uuid.uuid4().hex[:6]}")
    c = s.post(f"{API}/campaigns", json=payload).json()
    cid = c["id"]
    s.post(f"{API}/campaigns/{cid}/upload", files={"file": ("d.csv", _make_csv(2), "text/csv")})
    # confirm reading + upload_log exist
    assert len(s.get(f"{API}/campaigns/{cid}/readings").json()) == 2
    assert len(s.get(f"{API}/campaigns/{cid}/uploads").json()) == 1
    s.delete(f"{API}/campaigns/{cid}")
    # readings endpoint no longer belongs (campaign deleted)
    assert s.get(f"{API}/campaigns/{cid}").status_code == 404
    # cascade: readings should be gone
    assert s.get(f"{API}/campaigns/{cid}/readings").json() == []
    assert s.get(f"{API}/campaigns/{cid}/uploads").json() == []


def test_uploads_reverse_chrono(s, campaign):
    for _ in range(2):
        s.post(f"{API}/campaigns/{campaign['id']}/upload", files={"file": ("d.csv", _make_csv(1), "text/csv")})
    ups = s.get(f"{API}/campaigns/{campaign['id']}/uploads").json()
    assert len(ups) >= 2
    times = [u["uploaded_at"] for u in ups]
    assert times == sorted(times, reverse=True)
