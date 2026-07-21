# EcoReport AI — PRD

## Original Problem Statement
Build "EcoReport AI" — an Ambient Air Quality Monitoring Report Generation System that ingests raw hourly monitoring data (SO2, NO, NO2, NOx, CO, H2S, O3, PM10, PM2.5) plus meteorology (Temp, RH, Pressure, Wind Speed/Direction), and generates KSA-NCEC-compliant regulatory reports matching a reference BSA Lab report structure (cover, doc-control, TOC, exec summary, methodology, calibration, per-pollutant summary tables + time-series/rolling/wind-rose charts, compliance verdicts, conclusions, appendices with calibration certificates and NCEC license).

## Users & Personas
- **Environmental consultants / lab engineers (KSA)** — upload data, QA-flag rows, generate reports.
- **Site/project supervisors** — review campaigns and reports.
- **Regulators / clients** — recipients of the generated PDF reports (Phase 3+).

## Delivery approach
User requested strict phased delivery. Each phase verified before the next.
- **Phase 0** — Read reference report, produce structural breakdown, confirm understanding. ✅ done
- **Phase 1 — Schema + app skeleton (this phase).** ✅ done
- Phase 2 — Calculation engine (hourly/daily aggregates, 8-hr rolling for CO/O3, exceedance counting, wind-rose binning).
- Phase 3 — English report generation (PDF matching BSA reference structure).
- Phase 4 — Graphs (time-series, rolling, wind-rose, class-frequency).
- Phase 5 — Arabic / bilingual (RTL) support.
- Phase 6 — Report versioning.
- Phase 7 — Object storage for report artifacts + auth.

## Confirmed constraints (Phase 0/1)
- Raw data columns: `timestamp, SO2, NO, NO2, NOx, CO, H2S, O3, PM10, PM25, Temp, RH, Pressure, WindSpeed, WindDirection`.
- Units: pollutants µg/m³, Temp °C, RH %, Pressure hPa, WindSpeed m/s, WindDirection ° (0–360).
- Ingestion: CSV **and** XLSX, comma delimiter, ISO-8601 timestamps, hourly cadence.
- QA flag: **not present** in the file — user flags rows manually in the app.
- 8-hour rolling means for CO and O3 must display **blank/hidden** for the first 7 hours (insufficient data). **Not configurable.**
- Wind-rose speed bins: **configurable per campaign**; default preset `[Calm, 2.10-3.60, ≥3.60]`.

## Regulatory basis
- KSA NCEC 2020 Ambient Air Quality Standards (Royal Decree M/165, 19/11/1441 AH). Seeded on backend startup.
- USEPA reference methods cited (methodology only, no compliance role).

## Phase 1 — What's been implemented (2026-02)
### Backend (`/app/backend`)
- `models.py` — Pydantic v2 models: `Campaign`, `Reading`, `PollutantLimit`, `UploadLog`, `WindClassBin`.
- `db.py` — Motor client, ISO-string datetime helpers, NCEC seed, indexes.
- `routes/campaigns.py` — POST/GET/PUT/DELETE `/api/campaigns` (+ per-id detail).
- `routes/readings.py` — POST `/api/campaigns/{id}/upload` (CSV+XLSX), GET `/api/campaigns/{id}/readings`, GET `/api/campaigns/{id}/uploads`, PATCH `/api/readings/{id}` (manual flag), DELETE `/api/campaigns/{id}/readings`.
- `routes/limits.py` — GET `/api/limits` (read-only, seeded).
- `server.py` — FastAPI app, CORS, startup seed + indexes.

### Frontend (`/app/frontend`)
- Dark technical theme (Zinc/Slate + IBM Plex Sans/Mono) via design_agent guidelines.
- `AppShell` — sticky top nav (Campaigns, NCEC Limits) + Sonner Toaster.
- `CampaignsList` — dense list with status pill, coordinates (monospaced), reading counts, delete-with-confirm.
- `CampaignForm` — create/edit; sections for Project, Site, Monitoring window, Report metadata.
- `CampaignDetail` — 4 tabs (Overview, Readings, Settings, Reports placeholder).
  - Readings tab: dense monospaced table, per-row valid/invalid Switch, green/red row tints, clear-all with confirm.
  - Settings tab: wind-rose bin editor (add/remove rows, reset to defaults, save).
  - Reports tab: intentional placeholder for later phases.
- `UploadPage` — drag-and-drop dropzone, expected-columns preview, per-row error report.
- `LimitsPage` — dense read-only NCEC 2020 table, grouped by pollutant.
- Full `data-testid` coverage in `/app/frontend/src/constants/testIds/eco.js`.

## Not in Phase 1 (deferred by explicit user request)
- Calculation engine (aggregates, rolling means, exceedance counts) — Phase 2.
- Report generation, graphs, PDF export — Phase 3–4.
- Arabic/bilingual — Phase 5.
- Versioning — Phase 6.
- Auth + object storage for reports — Phase 7.

## Prioritized backlog
- **P0** — Verify Phase 1 with user, then begin Phase 2 calculation engine.
- **P1** — Accept the promised sample raw-data file to lock in real-world column casing / quirks.
- **P2** — Add campaign duplication ("clone" for repeat monitoring campaigns at same site).
