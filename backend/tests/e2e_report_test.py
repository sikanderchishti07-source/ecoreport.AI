"""End-to-end Phase 3 test: real Qiddiyah AQMS xls -> report DOCX.
Reuses the app's own ingest parsing helpers (no Mongo needed)."""
import sys, os
sys.path.insert(0, "/home/claude/ecoreport/backend")
os.environ.setdefault("MONGO_URL", "mongodb://x")
os.environ.setdefault("DB_NAME", "x")

from datetime import datetime, timedelta, timezone
import pandas as pd

from routes.readings import (_promote_header_if_needed, _normalize_columns,
                             _detect_timestamp_by_content)
from models import Campaign, Reading, PollutantLimit, POLLUTANT_FIELDS, ALL_MEASUREMENT_FIELDS
from db import NCEC_LIMITS
from report.generate import generate_report

XLS = "/mnt/project/tree_holding_facilities_project_qiddiyah.xls"

df = pd.read_excel(XLS, engine="xlrd")
print("raw columns:", list(df.columns)[:6], "... shape", df.shape)
df = _promote_header_if_needed(df)
df, recognized, ignored = _normalize_columns(df)
if "timestamp" not in df.columns:
    ts_col = _detect_timestamp_by_content(df)
    if ts_col:
        df = df.rename(columns={ts_col: "timestamp"})
print("recognized:", recognized)
print("ignored:", ignored)

readings = []
auto_flag_counts = {}
skipped = 0
for idx, row in df.iterrows():
    ts_raw = row.get("timestamp")
    if pd.isna(ts_raw):
        skipped += 1
        continue
    ts = pd.to_datetime(ts_raw)
    if ts.tzinfo is None:
        ts = ts.tz_localize(timezone.utc)
    kw = {"campaign_id": "qiddiyah-e2e", "timestamp": ts.to_pydatetime()}
    for f in ALL_MEASUREMENT_FIELDS:
        if f in df.columns:
            v = row[f]
            try:
                kw[f] = None if pd.isna(v) else float(v)
            except (TypeError, ValueError):
                kw[f] = None
    flags = []
    for pf in POLLUTANT_FIELDS:
        v = kw.get(pf)
        if v is not None and v < 0:
            flags.append(pf)
            kw[pf] = None
            auto_flag_counts[pf] = auto_flag_counts.get(pf, 0) + 1
    kw["auto_flagged_fields"] = flags
    readings.append(Reading(**kw))

readings.sort(key=lambda r: r.timestamp)
print(f"\ningested {len(readings)} readings, skipped {skipped}")
print("auto-flagged negative fields:", auto_flag_counts)
print("window:", readings[0].timestamp, "->", readings[-1].timestamp)

start = readings[0].timestamp.replace(minute=0, second=0, microsecond=0)
end = readings[-1].timestamp.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

campaign = Campaign(
    project_name="Tree Holding Facilities Project at Qiddiyah",
    client="Madar al Bea Environmental Consultant",
    site_name="Tree Holding Facilities Project at Qiddiyah Site",
    latitude=24.601500, longitude=46.318900,
    monitoring_start=start, monitoring_end=end,
    prepared_by="Eng. Aida Galal", project_supervision="Eng. Asim",
    report_number="BR-Q010426-001", revision="00",
    reporting_date=datetime(2026, 4, 20, tzinfo=timezone.utc),
)
limits = [PollutantLimit(**row) for row in NCEC_LIMITS]

out = "/home/claude/outputs_report/AAQ_Report_Qiddiyah_SAMPLE.docx"
path = generate_report(campaign, readings, limits, out,
                       charts_dir="/home/claude/outputs_report/charts")
print("\nreport written:", path, os.path.getsize(path), "bytes")

# --- Phase 5: Arabic, bilingual, and PDF outputs ---
out_ar = "/home/claude/outputs_report/AAQ_Report_Qiddiyah_SAMPLE_AR.docx"
generate_report(campaign, readings, limits, out_ar,
                charts_dir="/home/claude/outputs_report/charts", lang="ar")
print("AR report:", out_ar, os.path.getsize(out_ar), "bytes")

out_bi = "/home/claude/outputs_report/AAQ_Report_Qiddiyah_SAMPLE_BILINGUAL.docx"
generate_report(campaign, readings, limits, out_bi,
                charts_dir="/home/claude/outputs_report/charts", lang="bilingual")
print("Bilingual report:", out_bi, os.path.getsize(out_bi), "bytes")

from report.generate import convert_to_pdf
for p in (out_ar, out_bi):
    pdf = convert_to_pdf(p)
    print("PDF:", pdf, os.path.getsize(pdf), "bytes")
