# EcoReport AI — PRD

## Original Problem Statement
Build "EcoReport AI" — an Ambient Air Quality Monitoring Report Generation System that ingests raw hourly monitoring data (SO2, NO, NO2, NOx, CO, H2S, O3, PM10, PM2.5) plus meteorology (Temp, RH, Pressure, Wind Speed/Direction), and generates KSA-NCEC-compliant regulatory reports matching a reference BSA Lab report structure (cover, doc-control, TOC, exec summary, methodology, calibration, per-pollutant summary tables + time-series/rolling/wind-rose charts, compliance verdicts, conclusions, appendices with calibration certificates and NCEC license).

## Users & Personas
- Environmental consultants / lab engineers (KSA) — upload, QA-flag, generate.
- Site/project supervisors — review campaigns and reports.
- Regulators / clients — recipients of the generated PDF reports (Phase 3+).

## Delivery approach — phased (user-requested, verified per phase)
- **Phase 0** — Structural breakdown of reference report. ✅ done
- **Phase 1 — Schema + app skeleton.** ✅ done (this iteration)
- Phase 2 — Calculation engine.
- Phase 3 — English report generation.
- Phase 4 — Graphs (time-series, rolling, wind-rose, class-frequency).
- Phase 5 — Arabic / bilingual (RTL).
- Phase 6 — Report versioning.
- Phase 7 — Object storage + auth.

## Confirmed constraints (Phase 0/1)
- Raw data columns (canonical): `timestamp, SO2, NO, NO2, NOx, CO, H2S, O3, PM10, PM25, Temp, RH, Pressure, WindSpeed, WindDirection`.
- Units: pollutants µg/m³, Temp °C, RH %, Pressure hPa, WindSpeed m/s, WindDirection ° (0–360).
- Ingestion: **CSV, XLSX, and XLS** (with `xlrd`). ISO-8601 timestamps. Hourly cadence.
- QA flag not present in raw file — user flags rows manually via the app.
- 8-hour rolling means (CO, O3) must display blank/hidden for the first 7 hours (insufficient data). Not configurable.
- Wind-rose speed bins configurable per campaign; default `[Calm, 2.10-3.60, ≥3.60]`.

## Real-world vendor file adaptation (learned from `tree holding facilities project qiddiyah.xls`)
- Vendor exports the file with **two-row header**: row 0 has merged "AQMS" cells (pandas reads them as `Unnamed: 0`, `AQMS`, `AQMS.1`…); row 1 has the actual parameter names (`AMBTEMP, BARPRESS, OZONE, NOX, WDR, WSP, RELHUM, …`); row 2 is a `Date` sub-label; data starts row 3.
- Added `_promote_header_if_needed` heuristic to detect merged-header pattern and promote the parameter row; and `_detect_timestamp_by_content` to pick up the timestamp column even when its header cell is blank.
- Vendor exports include analyzer flow rates + aux met: `COFlow, SO2Flow, PMFlow, PMCoarse, RAINFALL, SOLARRAD`. These are transparently reported as "ignored columns" (schema-out-of-scope) but do NOT block ingestion.
- Values below detection limit come through as negatives (e.g. `NO=-1.36, H2S=-16.69`). Currently stored raw. **Phase 2 decision**: keep raw and floor to 0 for compliance/statistics? Or preserve as-is? Need user answer.
- Analyzer warm-up hours (all-NaN except one aux column) are ingested as valid empty rows — expected behavior.

## Regulatory basis
KSA NCEC 2020 (Royal Decree M/165, 19/11/1441 AH). 14 limits seeded on startup. USEPA methods cited (methodology only).

## Phase 1 — What's been implemented (2026-02)
### Backend (`/app/backend`)
- `models.py` — Pydantic v2: Campaign, Reading, PollutantLimit, UploadLog (with `recognized_columns` + `ignored_columns`), WindClassBin, DEFAULT_WIND_BINS.
- `db.py` — Motor client, ISO-string datetime helpers, NCEC seed, indexes.
- `routes/campaigns.py` — POST/GET/PUT/DELETE `/api/campaigns` (+cascade).
- `routes/readings.py` — CSV/XLSX/XLS ingest with vendor-header auto-detect + timestamp-by-content fallback, per-campaign readings list, manual flag PATCH, clear-all DELETE, upload-log GET.
- `routes/limits.py` — GET `/api/limits`.
- `server.py` — FastAPI app + startup seed + indexes.

### Frontend (`/app/frontend`)
- Dark technical theme (Zinc/Slate + IBM Plex Sans/Mono).
- AppShell (sticky top nav + Sonner toaster).
- CampaignsList (dense list, status pills, delete-with-confirm).
- CampaignForm (create/edit; Project/Site/Window/Report-metadata sections).
- CampaignDetail (4 tabs: Overview · Readings · Settings · Reports placeholder).
  - Readings: dense monospaced table, per-row Switch flag, red row tint for invalid, sticky header + timestamp col, clear-all with confirm.
  - Settings: wind-rose bin editor (add/remove/reset/save).
- UploadPage (drag-drop dropzone, expected-columns preview, **recognized/ignored column pills**, per-row error report).
- LimitsPage (dense read-only NCEC 2020 table).
- Full `data-testid` coverage in `constants/testIds/eco.js`.

### Testing
- testing_agent_v3 iteration 1: **14/14 backend + all critical frontend flows passed**.
- Real vendor `.xls` verified via manual curl + Playwright: **25 rows ingested, 0 skipped, 15 recognized, 6 ignored** — no code changes needed after adaptation.

## Phase 2 — Locked scope (waiting on averaging-period table before coding)

### Data-quality rules (finalised)
1. **Negative pollutant readings** → field-level auto-null on ingest, tracked in `Reading.auto_flagged_fields`, excluded from all calculations. Applies to `SO2, NO, NO2, NOx, CO, H2S, O3, PM10, PM25` only (meteorology not affected). ✅ implemented Phase 1.
2. **75 % data-capture completeness gate** — for each pollutant × averaging period, if `valid_readings / expected_readings < 0.75`, replace all statistics/compliance verdicts/exceedance counts for that pollutant × period with the literal string **"insufficient data — not reportable"**.
   - "Valid" = not auto-flagged AND not manually-flagged AND not null.
   - Missing hours (no row in DB) count against capture.
   - **Expected readings are pro-rated to the actual monitoring-window hours** that fall inside the averaging period (locked default).
   - **Annual rows** are always shown even for short campaigns; if the campaign is shorter than the annual window, the row displays "insufficient data — not reportable" rather than being omitted (locked default).

### Evaluation rules per averaging period
| Period | Expected | Insufficient condition | On insufficient |
|---|---|---|---|
| 1-hr summary | campaign monitoring-hours | campaign valid-hours / monitoring-hours < 75 % | Max/Min/Daily-avg + exceedance count = "insufficient data — not reportable" |
| 8-hr rolling (CO, O₃) | 8 hourly values in `[t−7h, t]` | < 6 valid hours in the window | Blank rolling value at t; campaign-level summary marked "insufficient" if valid-rolling / possible-rolling < 75 % |
| 24-hr daily | 24 hourly values per day (prorated for partial days) | day has < 18 valid hours → day = insufficient; campaign-level summary insufficient if valid-days / total-days < 75 % | Daily line hidden; summary text |
| 1-year | 1 valid daily value per calendar day | valid-days / 365 (or 366) < 75 % | Annual row always shown with the "insufficient" text |

### 8-hr rolling first-7-hours rule (from Phase 0)
Blank/hidden for the first 7 hours (insufficient window), non-configurable. Not a 75 % violation — just a warm-up gap.

### Wind-rose bins
Configurable per campaign, default `[Calm, 2.10-3.60, ≥3.60]`. Already implemented Phase 1.

### Still open before Phase 2 coding starts
- **Averaging-period table from user's reference report** — expected in next user message. Will be reconciled against seeded KSA NCEC 2020 limits (from BSA Table 5) before code lands.

## Prioritized backlog
- **P0 (blocked on user)** — Averaging-period table → then start Phase 2 calc engine.
- **P1** — Campaign duplication ("clone") action.
- **P1** — Timezone handling: sample data is naïve; report must be "KSA time" per §2.5.4. Consider explicit timezone field on Campaign.
- **P2** — QA audit-trail CSV export (every excluded reading + reason) for regulatory defensibility.
