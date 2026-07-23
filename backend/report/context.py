"""Builds the docxtpl rendering context from a CampaignSummary.

All numeric formatting, adaptive narrative sentences ("did not exceed" vs
exceedance wording vs insufficient-data wording), and the report's table rows
are produced here, so the template stays purely structural.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from models import Campaign, CampaignSummary, PeriodEvaluation, PollutantEvaluation

from units_mdl import format_with_mdl
from report.i18n_dynamic import (ALLOWANCE, CAPTURE_ROW_NAMES, DYN, FIG_REFS,
                                 PERIOD_ADJ, PERIOD_NAMES,
                                 POLLUTANT_NARRATIVE_NAMES, days_text, fmt_date)

NR = "N/R*"          # not reportable marker used inside tables


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


def _footnote(evals: List[PeriodEvaluation], lang: str = "en") -> str:
    """Adaptive footnote under each summary table:
    - any non-compliant verdict -> exceedance statement
    - all observed exceedance counts zero -> classic 'no exceedances' line
    - exceedances observed but allowance not evaluable -> informational note."""
    D = DYN[lang]
    evals = [e for e in evals if e is not None]
    if any(e.verdict == "non-compliant" for e in evals):
        periods = ", ".join(PERIOD_NAMES[lang][e.averaging_period]
                            for e in evals if e.verdict == "non-compliant")
        return D["fn_noncompliant"].format(periods=periods)
    if all(e.exceedance_count == 0 for e in evals):
        return D["fn_clean"]
    n = sum(e.exceedance_count for e in evals)
    return D["fn_informational"].format(n=n)


def _compliance_sentence(evals: List[PeriodEvaluation], periods_text: str,
                         lang: str = "en") -> str:
    D = DYN[lang]
    evals = [e for e in evals if e is not None]
    if any(e.verdict == "non-compliant" for e in evals):
        return D["cs_noncompliant"].format(periods=periods_text)
    if all(e.exceedance_count == 0 for e in evals):
        return D["cs_clean"].format(periods=periods_text)
    return D["cs_informational"]


def _daily_avg(p: PollutantEvaluation) -> Optional[float]:
    """'Daily average' in the gold-standard tables = period mean. Use the 24-hr
    evaluation mean when available, else the hourly mean."""
    e24 = _period(p, "24 Hour")
    if e24 is not None and e24.mean_value is not None:
        return e24.mean_value
    return p.hourly_mean


def build_context(campaign: Campaign, summary: CampaignSummary,
                  lang: str = "en") -> Dict:
    D = DYN[lang]
    P: Dict[str, PollutantEvaluation] = {p.pollutant: p for p in summary.pollutants}
    hours = summary.monitoring_hours
    start = summary.monitoring_start
    end = summary.monitoring_end
    window_text = D["window_to"].format(a=fmt_date(start, lang, with_time=True),
                                        b=fmt_date(end, lang, with_time=True))
    days = max(round(hours / 24), 1)
    period_text = days_text(days, lang)

    def pol_ctx(key: str, table_periods: List[str], narrative_name: str,
                fig_refs: str, extra_8h: bool = False) -> Dict:
        p = P[key]
        _mdl = getattr(p, "mdl_ugm3", None)

        def fmtm(v):
            """Display '<MDL' when a value sits below the detection limit."""
            if v is None:
                return fmt(v)
            s = format_with_mdl(v, _mdl)
            return s if s is not None else fmt(v)

        evs = [_period(p, per) for per in table_periods]
        e1 = _period(p, "1 Hour")
        e8 = _period(p, "8 Hour (rolling)")
        e24 = _period(p, "24 Hour")
        d: Dict = {
            "capture": fmt(p.hourly_capture_pct),
            "h_max": fmtm(p.hourly_max),
            "h_min": fmtm(p.hourly_min),
            "daily_avg": fmtm(_daily_avg(p)),
            "footnote": _footnote(evs, lang) + (
                ("\n" + D["mdl_footnote"].format(
                    mdl=f"{_mdl:.1f}", n=getattr(p, "below_mdl_count", 0))
                 if (_mdl and getattr(p, "below_mdl_count", 0)) else "") + (
                "\n" + D["nr_footnote"] if any(
                    v == NR for v in (fmt(p.hourly_max), fmt(p.hourly_min))
                ) else "")),
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
        periods_text = D["join_and"].join(
            PERIOD_ADJ[lang][per] for per in table_periods)
        d["narrative"] = (
            D["narrative"].format(
                name=POLLUTANT_NARRATIVE_NAMES[lang][key], hours=hours,
                figs=FIG_REFS[lang][fig_refs])
            + _compliance_sentence(evs, periods_text, lang))
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
            D["narrative_group_nox"].format(
                name=POLLUTANT_NARRATIVE_NAMES[lang]["NOX_GROUP"], hours=hours)
            + _compliance_sentence([_period(P["NO2"], "1 Hour")],
                                   PERIOD_ADJ[lang]["1 Hour"], lang)
            + D["nox_supporting"]),
        "footnote": _footnote([_period(P["NO2"], "1 Hour")], lang),
    }
    pm_group = {
        "narrative": (
            D["narrative_group_pm"].format(
                name=POLLUTANT_NARRATIVE_NAMES[lang]["PM_GROUP"], hours=hours)
            + _compliance_sentence(
                [_period(P["PM10"], "24 Hour"), _period(P["PM25"], "24 Hour")],
                PERIOD_ADJ[lang]["24 Hour"], lang)),
    }

    # Table 1 — data capture rows
    met = summary.meteorology
    def cap_row(name, cap_pct, valid=None):
        avail = valid if valid is not None else round(cap_pct / 100.0 * hours)
        return {"name": name, "total": str(hours), "available": str(avail),
                "exception": str(hours - avail), "capture": fmt(cap_pct)}

    CR = CAPTURE_ROW_NAMES[lang]
    capture_rows = [
        cap_row(CR["temp"], met.temp_capture_pct),
        cap_row(CR["rh"], met.rh_capture_pct),
        cap_row(CR["pressure"], met.pressure_capture_pct),
        cap_row(CR["wd"], met.wind_direction_capture_pct),
        cap_row(CR["ws"], met.wind_speed_capture_pct),
    ] + [
        cap_row(CR["pollutant"].format(sym=lbl), P[key].hourly_capture_pct,
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
        D["capture_all_100"] if all_100 else
        D["capture_partial"].format(pct=fmt(summary.overall_hourly_capture_pct)))

    # NCEC Table 5 rows (from campaign summary's evaluations for consistency)
    ncec_rows = []
    for key, lbl in [("SO2", "SO₂"), ("CO", "CO"), ("O3", "O3"), ("H2S", "H₂S"),
                     ("NO2", "NO2"), ("PM10", "PM10"), ("PM25", "PM2.5")]:
        for e in P[key].period_evaluations:
            allowance = e.allowance_description or "None"
            ncec_rows.append({
                "pollutant": lbl,
                "period": PERIOD_NAMES[lang][e.averaging_period],
                "limit": fmt_limit(e.limit_ugm3),
                "allowance": ALLOWANCE[lang].get(allowance, allowance),
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
        lines = [D["concl_hmax"].format(v=fmt(p.hourly_max))
                 + (D["concl_8hmax"].format(v=fmt(p.rolling_8h_max))
                    if has_8h else "")]
        evs = [e for e in p.period_evaluations
               if e.averaging_period != "1 Year"]
        if any(e.verdict == "non-compliant" for e in evs):
            lines.append(D["concl_exceed"])
        elif all(e.exceedance_count == 0 for e in evs):
            lines.append(D["concl_clean"])
        else:
            lines.append(D["concl_informational"])
        lines.append(D["concl_davg"].format(v=fmt(_daily_avg(p))))
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
        appendix1 = D["app1_none"]
    else:
        parts = []
        if n_auto:
            parts.append(D["app1_auto"].format(n=n_auto))
        if n_flagged:
            parts.append(D["app1_manual"].format(n=n_flagged))
        appendix1 = D["app1_wrap"].format(parts=D["join_semi"].join(parts))

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
        "reporting_date": (fmt_date(campaign.reporting_date, lang)
                           if campaign.reporting_date else "—"),
        "prepared_by": campaign.prepared_by or "—",
        "project_supervision": campaign.project_supervision or "—",
        # window
        "monitoring_hours": hours,
        "monitoring_period_text": period_text,
        "monitoring_start_date": fmt_date(start, lang),
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
        "met_conclusion_1": D["met1"].format(mx=fmt(met.temp_max),
                                             mn=fmt(met.temp_min)),
        "met_conclusion_2": D["met2"].format(mx=fmt(met.rh_max),
                                             mn=fmt(met.rh_min)),
        "met_conclusion_3": D["met3"].format(mx=fmt(met.pressure_max),
                                             mn=fmt(met.pressure_min)),
        "met_conclusion_4": D["met4"].format(mx=fmt(met.wind_speed_max),
                                             mn=fmt(met.wind_speed_min)),
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
