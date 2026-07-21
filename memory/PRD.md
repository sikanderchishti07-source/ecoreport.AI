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

## Prioritized backlog
- **P0** — User confirms Phase 1 (schema + skeleton + vendor adapter) → start Phase 2 calc engine.
- **P0** — In Phase 2, confirm treatment of negative (below-detection) values in compliance/statistics.
- **P1** — Campaign duplication ("clone") action for repeat monitoring campaigns at same site.
- **P2** — Timezone handling: sample data is naïve; report must be "KSA time" per §2.5.4. Consider explicit timezone field on Campaign.
