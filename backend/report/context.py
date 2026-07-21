"""Builds the docxtpl rendering context from a CampaignSummary.

All numeric formatting, adaptive narrative sentences ("did not exceed" vs
exceedance wording vs insufficient-data wording), and the report's table rows
are produced here, so the template stays purely structural.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from models import Campaign, CampaignSummary, PeriodEvaluation, PollutantEvaluation

NR = "N/R*"          # not reportable marker used inside tables
NR_FOOTNOTE = ("*N/R: insufficient data — not reportable (data capture below 75% "
               "for this averaging period).")


def fmt(v: Optional[float], dp: int = 1) -> str:
    if v is None:
        return NR
    return f"{v:,.{dp}f}" if dp else f"{v:,.0f}"


def fmt_limit(v: float) -> str:
    return f"{v:,.0f}"


def _period(p: PollutantEvaluation, label: str) -> Optional[PeriodEvaluation]:
    for e in p.period_evaluations:
        if e.averaging_period == label:
            return e
    return None


def _footnote(evals: List[PeriodEvaluation]) -> str:
    """Adaptive footnote under each summary table:
    - any non-compliant verdict -> exceedance statement
    - all observed exceedance counts zero -> classic 'no exceedances' line
    - exceedances observed but allowance not evaluable -> informational note."""
    evals = [e for e in evals if e is not None]
    if any(e.verdict == "non-compliant" for e in evals):
        periods = ", ".join(e.averaging_period for e in evals
                            if e.verdict == "non-compliant")
        return (f"*Exceedance(s) of the NCEC standard were recorded for the "
                f"{periods} averaging period(s).")
    if all(e.exceedance_count == 0 for e in evals):
        return "*There were no exceedances of NCEC standards."
    n = sum(e.exceedance_count for e in evals)
    return (f"*{n} value(s) above the NCEC exceedance level were observed; the "
            f"applicable allowance is defined over a longer reference period than "
            f"this monitoring campaign, so the count is reported for information "
            f"only.")


def _compliance_sentence(evals: List[PeriodEvaluation], periods_text: str) -> str:
    evals = [e for e in evals if e is not None]
    if any(e.verdict == "non-compliant" for e in evals):
        return (f"Accordingly, exceedances of the permissible limits in NCEC "
                f"{periods_text} standards were recorded.")
    if all(e.exceedance_count == 0 for e in evals):
        return (f"Accordingly, the results did not exceed the permissible limits "
                f"in NCEC {periods_text} standards.")
    return (f"Values above the NCEC exceedance level were observed; the applicable "
            f"allowance is defined over a longer reference period than this "
            f"monitoring campaign and the observed count is therefore reported "
            f"for information only.")


def _daily_avg(p: PollutantEvaluation) -> Optional[float]:
    """'Daily average' in the gold-standard tables = period mean. Use the 24-hr
    evaluation mean when available, else the hourly mean."""
    e24 = _period(p, "24 Hour")
    if e24 is not None and e24.mean_value is not None:
        return e24.mean_value
    return p.hourly_mean


def build_context(campaign: Campaign, summary: CampaignSummary) -> Dict:
    P: Dict[str, PollutantEvaluation] = {p.pollutant: p for p in summary.pollutants}
    hours = summary.monitoring_hours
    start = summary.monitoring_start
    end = summary.monitoring_end
    window_text = (f"{start.strftime('%B %d, %Y, %I:%M %p').replace(' 0', ' ')} to "
                   f"{end.strftime('%B %d, %Y, %I:%M %p').replace(' 0', ' ')}")
    days = max(round(hours / 24), 1)
    period_text = "one day" if days == 1 else f"{days} days"

    def pol_ctx(key: str, table_periods: List[str], narrative_name: str,
                fig_refs: str, extra_8h: bool = False) -> Dict:
        p = P[key]
        evs = [_period(p, per) for per in table_periods]
        e1 = _period(p, "1 Hour")
        e8 = _period(p, "8 Hour (rolling)")
        e24 = _period(p, "24 Hour")
        d: Dict = {
            "capture": fmt(p.hourly_capture_pct),
            "h_max": fmt(p.hourly_max),
            "h_min": fmt(p.hourly_min),
            "daily_avg": fmt(_daily_avg(p)),
            "footnote": _footnote(evs) + (
                f"\n{NR_FOOTNOTE}" if any(
                    v == NR for v in (fmt(p.hourly_max), fmt(p.hourly_min))
                ) else ""),
        }
        if e1:
            d["limit_1h"] = fmt_limit(e1.limit_ugm3)
            d["exceed_1h"] = str(e1.exceedance_count)
        if e8:
            d["limit_8h"] = fmt_limit(e8.limit_ugm3)
            d["exceed_8h"] = str(e8.exceedance_count)
            d["r8_max"] = fmt(p.rolling_8h_max)
            d["r8_min"] = fmt(p.rolling_8h_min)
        if e24:
            d["limit_24h"] = fmt_limit(e24.limit_ugm3)
            d["exceed_24h"] = str(e24.exceedance_count)
        periods_text = " & ".join(
            {"1 Hour": "hourly", "24 Hour": "daily",
             "8 Hour (rolling)": "8-hour"}[per] for per in table_periods)
        d["narrative"] = (
            f"The recorded data of {narrative_name} was captured for {hours} hours "
            f"at the location. The results were summarized in the following table, "
            f"and represented on {fig_refs} which includes the maximum permissible "
            f"limits in NCEC's 2020 ambient air quality standards. "
            + _compliance_sentence(evs, periods_text))
        return d

    so2 = pol_ctx("SO2", ["1 Hour", "24 Hour"], "Sulphur dioxide (SO2)", "a graph")
    no2 = pol_ctx("NO2", ["1 Hour"], "Nitrogen dioxide (NO2)", "graphs")
    co = pol_ctx("CO", ["1 Hour", "8 Hour (rolling)"], "Carbon Monoxide (CO)",
                 "a graph", extra_8h=True)
    h2s = pol_ctx("H2S", ["1 Hour", "24 Hour"], "Hydrogen sulfide (H2S)", "a graph")
    o3 = pol_ctx("O3", ["8 Hour (rolling)"], "Ozone (O3)", "graphs")
    pm10 = pol_ctx("PM10", ["24 Hour"], "Particulate Matter (PM10)", "a graph")
    pm25 = pol_ctx("PM25", ["24 Hour"], "Particulate Matter (PM2.5)", "a graph")

    def supporting_ctx(key: str) -> Dict:
        p = P[key]
        return {
            "capture": fmt(p.hourly_capture_pct),
            "h_max": fmt(p.hourly_max),
            "h_min": fmt(p.hourly_min),
            "daily_avg": fmt(p.hourly_mean),
        }

    no = supporting_ctx("NO")
    nox = supporting_ctx("NOx")

    nox_group = {
        "narrative": (
            f"The recorded data of Oxides of Nitrogen (NO, NO2, NOx) was captured "
            f"for {hours} hours at the location. The results were summarized in the "
            f"following table, and represented on graphs which include the maximum "
            f"permissible limits in NCEC's 2020 ambient air quality standards. "
            + _compliance_sentence([_period(P["NO2"], "1 Hour")], "hourly")
            + " NO and NOx have no applicable NCEC limit and are reported as "
              "supporting data only."),
        "footnote": _footnote([_period(P["NO2"], "1 Hour")]),
    }
    pm_group = {
        "narrative": (
            f"The recorded data of Particulate Matter (PM10 & PM2.5) was captured "
            f"for {hours} hours at the location. The results were summarized in the "
            f"following tables, and represented on graphs which include the maximum "
            f"permissible limits in NCEC's 2020 ambient air quality standards. "
            + _compliance_sentence(
                [_period(P["PM10"], "24 Hour"), _period(P["PM25"], "24 Hour")],
                "daily")),
    }

    # Table 1 — data capture rows
    met = summary.meteorology
    def cap_row(name, cap_pct, valid=None):
        avail = valid if valid is not None else round(cap_pct / 100.0 * hours)
        return {"name": name, "total": str(hours), "available": str(avail),
                "exception": str(hours - avail), "capture": fmt(cap_pct)}

    capture_rows = [
        cap_row("Temp. (°C)", met.temp_capture_pct),
        cap_row("Humidity (%)", met.rh_capture_pct),
        cap_row("Pressure (hPa)", met.pressure_capture_pct),
        cap_row("Wind Direction (°)", met.wind_direction_capture_pct),
        cap_row("Wind Speed (m/s)", met.wind_speed_capture_pct),
    ] + [
        cap_row(f"{lbl} (µg/m³)", P[key].hourly_capture_pct,
                P[key].hourly_valid_count)
        for key, lbl in [("NO", "NO"), ("NO2", "NO₂"), ("NOx", "NOx"),
                         ("O3", "O₃"), ("H2S", "H₂S"), ("CO", "CO"),
                         ("SO2", "SO₂"), ("PM10", "PM10"), ("PM25", "PM2.5")]
    ]

    capture_vals = [P[k].hourly_capture_pct for k in
                    ("SO2", "NO2", "CO", "H2S", "O3", "PM10", "PM25")]
    all_100 = all(abs(v - 100.0) < 1e-9 for v in capture_vals) and all(
        abs(v - 100.0) < 1e-9 for v in
        [met.temp_capture_pct, met.rh_capture_pct, met.pressure_capture_pct,
         met.wind_speed_capture_pct, met.wind_direction_capture_pct])
    capture_sentence = (
        "Hourly data capture rates are 100% for all the monitored parameters at "
        "the location." if all_100 else
        f"The average hourly data capture rate across the monitored parameters at "
        f"the location was {fmt(summary.overall_hourly_capture_pct)}%. Parameters "
        f"below the 75% data-capture requirement are marked as not reportable in "
        f"the relevant tables.")

    # NCEC Table 5 rows (from campaign summary's evaluations for consistency)
    ncec_rows = []
    for key, lbl in [("SO2", "SO₂"), ("CO", "CO"), ("O3", "O3"), ("H2S", "H₂S"),
                     ("NO2", "NO2"), ("PM10", "PM10"), ("PM25", "PM2.5")]:
        for e in P[key].period_evaluations:
            ncec_rows.append({
                "pollutant": lbl,
                "period": e.averaging_period,
                "limit": fmt_limit(e.limit_ugm3),
                "allowance": e.allowance_description or "None",
            })

    # Wind tables
    wr = summary.wind_rose
    non_calm = [b.label for b in wr.bins
                if b.label.strip().lower() not in ("calm", "calms")]
    wind_pct_rows, wind_count_rows = [], []
    for i, row in enumerate(wr.direction_rows, start=1):
        pct_vals = [(row.counts_by_class.get(c, 0) / wr.total_valid * 100.0)
                    if wr.total_valid else 0.0 for c in non_calm]
        wind_pct_rows.append({
            "direction": f"{i} {row.direction}",
            "vals": [f"{v:.5f}" if v else "0.00" for v in pct_vals],
            "total": f"{sum(pct_vals):.5f}" if sum(pct_vals) else "0.00",
        })
        cnt_vals = [row.counts_by_class.get(c, 0) for c in non_calm]
        wind_count_rows.append({
            "direction": f"{i} {row.direction}",
            "vals": [str(v) for v in cnt_vals],
            "total": str(sum(cnt_vals)),
        })
    pct_totals = [f"{wr.class_frequency_pct.get(c, 0.0):.5f}" for c in non_calm]
    cnt_totals = [str(wr.class_totals.get(c, 0)) for c in non_calm]
    non_calm_total = sum(wr.class_totals.get(c, 0) for c in non_calm)

    # Conclusions
    def conclusion(key: str, title: str, has_8h=False) -> Dict:
        p = P[key]
        lines = [f"The hourly maximum concentration was {fmt(p.hourly_max)} µg/m³."
                 + (f" The 8-hour maximum concentration was "
                    f"{fmt(p.rolling_8h_max)} µg/m³." if has_8h else "")]
        evs = [e for e in p.period_evaluations
               if e.averaging_period != "1 Year"]
        if any(e.verdict == "non-compliant" for e in evs):
            lines.append("Exceedance(s) of NCEC standards were recorded.")
        elif all(e.exceedance_count == 0 for e in evs):
            lines.append("There were no exceedances of NCEC standards.")
        else:
            lines.append("Observed values above the NCEC exceedance level are "
                         "reported for information only (allowance reference "
                         "period exceeds the campaign length).")
        lines.append(f"The daily average concentration was "
                     f"{fmt(_daily_avg(p))} µg/m³.")
        return {"title": title, "lines": lines}

    conclusion_blocks = [
        conclusion("PM10", "PM10"),
        conclusion("PM25", "PM2.5"),
        conclusion("O3", "O3", has_8h=True),
        conclusion("SO2", "SO2"),
        conclusion("NO2", "NO2"),
        conclusion("H2S", "H2S"),
        conclusion("CO", "CO", has_8h=True),
    ]

    # Appendix 1 — data exceptions from flags
    n_flagged = summary.manually_flagged_readings
    n_auto = summary.auto_flagged_readings
    if n_flagged == 0 and n_auto == 0:
        appendix1 = ("No Data Exception due to the short period of monitoring and "
                     "all maintenance and multipoint calibration took place before "
                     "and after the monitoring time.")
    else:
        parts = []
        if n_auto:
            parts.append(f"{n_auto} hourly record(s) contained negative pollutant "
                         f"values that were invalidated at field level as "
                         f"instrument/calibration artifacts")
        if n_flagged:
            parts.append(f"{n_flagged} hourly record(s) were manually invalidated "
                         f"during data validation")
        appendix1 = ("Data exceptions during the monitoring period: "
                     + "; ".join(parts) + ". All remaining data were validated "
                     "per the procedures in Section 2.5.")

    # Table 4 — instruments (campaign override later; gold-standard defaults now)
    instruments = getattr(campaign, "instruments", None) or [
        {"parameter": "O3", "sn": "3504",
         "technique": "T-400 (TELEDYNE) EQOA-0992-087"},
        {"parameter": "NO, NO2, NOX", "sn": "4255",
         "technique": "T-200 (TELEDYNE) RFNA-1194-099"},
        {"parameter": "CO", "sn": "3410",
         "technique": "T-300 (TELEDYNE) RFCA-1093-093"},
        {"parameter": "SO₂", "sn": "3434",
         "technique": "T-100 (TELEDYNE) EQSA-0495-100"},
        {"parameter": "H₂S", "sn": "587",
         "technique": "T-101 (TELEDYNE) EQSA-0495-100 per 40 CFR Part 53"},
        {"parameter": "DILUTION CALIBRATOR", "sn": "4619", "technique": "NA"},
        {"parameter": "ZERO AIR GENERATOR", "sn": "4630", "technique": "NA"},
        {"parameter": "AMBIENT TEMPERATURE", "sn": "031194",
         "technique": "41382 VF-METONE-USA"},
        {"parameter": "BAROMETRIC PRESSURE", "sn": "Y16801",
         "technique": "092-METONE-USA"},
        {"parameter": "RELATIVE HUMIDITY", "sn": "031194",
         "technique": "41382 VF-METONE-USA"},
        {"parameter": "WIND SPEED, WIND DIRECTION", "sn": "168369",
         "technique": "RM YOUNG-USA"},
        {"parameter": "PM10 / PM2.5", "sn": "CM13361012",
         "technique": "Thermo Scientific Model 5014i Beta continuous "
                      "particulate monitor"},
    ]

    return {
        # identity / metadata
        "project_name": campaign.project_name,
        "client": campaign.client,
        "provider": campaign.provider,
        "provider_short": campaign.provider.split("(")[-1].rstrip(")")
        if "(" in campaign.provider else campaign.provider,
        "provider_legal_name": "Bander Said Allehiany for Environmental Consultancy",
        "provider_tel": "00966114611939",
        "provider_fax": "00966114659739",
        "provider_address": "Riyadh 11351 – Kingdom Saudi Arabia",
        "provider_email": "Info@alemadonline.com",
        "site_name": campaign.site_name,
        "latitude": f"{campaign.latitude:.6f}",
        "longitude": f"{campaign.longitude:.6f}",
        "inlet_height_m": f"{campaign.inlet_height_m:g}",
        "report_number": campaign.report_number or "—",
        "revision": campaign.revision,
        "reporting_date": (campaign.reporting_date.strftime("%d %B %Y")
                           if campaign.reporting_date else "—"),
        "prepared_by": campaign.prepared_by or "—",
        "project_supervision": campaign.project_supervision or "—",
        # window
        "monitoring_hours": hours,
        "monitoring_period_text": period_text,
        "monitoring_start_date": start.strftime("%B %d, %Y"),
        "monitoring_window_text": window_text,
        "overall_capture": fmt(summary.overall_hourly_capture_pct),
        "capture_sentence": capture_sentence,
        "capture_rows": capture_rows,
        # standards
        "ncec_rows": ncec_rows,
        "instruments": instruments,
        # pollutants
        "so2": so2, "no2": no2, "no": no, "nox": nox, "co": co, "h2s": h2s,
        "o3": o3, "pm10": pm10, "pm25": pm25,
        "nox_group": nox_group, "pm_group": pm_group,
        # meteorology
        "met": {
            "temp_capture": fmt(met.temp_capture_pct),
            "temp_max": fmt(met.temp_max), "temp_min": fmt(met.temp_min),
            "rh_capture": fmt(met.rh_capture_pct),
            "rh_max": fmt(met.rh_max), "rh_min": fmt(met.rh_min),
            "pressure_capture": fmt(met.pressure_capture_pct),
            "pressure_max": fmt(met.pressure_max),
            "pressure_min": fmt(met.pressure_min),
            "ws_capture": fmt(met.wind_speed_capture_pct),
            "ws_max": fmt(met.wind_speed_max), "ws_min": fmt(met.wind_speed_min),
            "ws_mean": fmt(met.wind_speed_mean),
            "prevailing": met.prevailing_wind_direction or "—",
        },
        "met_conclusion_1": (
            f"Hourly maximum and minimum temperatures were {fmt(met.temp_max)} °C "
            f"and {fmt(met.temp_min)} °C, respectively."),
        "met_conclusion_2": (
            f"Hourly maximum and minimum relative humidity were {fmt(met.rh_max)} % "
            f"and {fmt(met.rh_min)} %, respectively."),
        "met_conclusion_3": (
            f"Hourly maximum and minimum barometric pressure were "
            f"{fmt(met.pressure_max)} hPa and {fmt(met.pressure_min)} hPa, "
            f"respectively."),
        "met_conclusion_4": (
            f"The maximum and minimum hourly wind speed were {fmt(met.wind_speed_max)} "
            f"m/s and {fmt(met.wind_speed_min)} m/s, respectively."),
        # wind tables
        "wind_class_labels": non_calm,
        "wind_pct_rows": wind_pct_rows,
        "wind_pct_totals": pct_totals,
        "wind_pct_totals_grand": (
            f"{sum(wr.class_frequency_pct.get(c, 0.0) for c in non_calm):.2f}"),
        "wind_pct_totals_calms": f"{wr.calms_pct:.2f}",
        "wind_pct_totals_missing": f"{max(hours - wr.total_valid, 0)}",
        "wind_count_rows": wind_count_rows,
        "wind_count_totals": cnt_totals,
        "wind_count_totals_grand": str(non_calm_total),
        "wind_count_totals_calms": str(wr.calms_count),
        "wind_count_totals_missing": str(max(hours - wr.total_valid, 0)),
        # conclusions & appendix
        "conclusion_blocks": conclusion_blocks,
        "appendix1_text": appendix1,
    }
