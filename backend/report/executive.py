"""Executive-level content: the parts an international consultancy report has
that a bare compliance record does not.

Everything here is derived from the campaign and its computed summary — no
figure is invented, and no interpretation is offered beyond what the data
states. Specifically:

* the **compliance summary** restates results already in the pollutant tables,
  on one page, so a reviewer can answer "did it pass?" without reading eight
  tables;
* the **headline finding** states the outcome in the first paragraph of the
  Executive Summary rather than on the final page;
* **recommendations** are drafted from the results themselves (capture,
  exceedances, proximity to limits) and are deliberately conservative;
* the **limitations statement** is standard reliance wording, which the
  provider should have reviewed once by their own advisers before issue;
* **measurement uncertainty** is quoted from the calibration certificates;
* the **site geometry** paragraph states the bearing and distance between the
  station and the facility, and the prevailing wind — as measurements. It
  draws no upwind/downwind conclusion: that interpretation belongs to the
  consultant commissioning the survey, not to the measuring laboratory.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

COMPASS_16 = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
              "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]

DISPLAY = {"SO2": "SO₂", "NO2": "NO₂", "NOx": "NOₓ", "NO": "NO", "CO": "CO",
           "O3": "O₃", "H2S": "H₂S", "PM10": "PM10", "PM25": "PM2.5"}

# Default expanded uncertainty from the gas calibration certificates
DEFAULT_UNCERTAINTY = "±2% (k = 2, approximately 95% confidence)"


def _fmt(v: Optional[float], d: int = 1) -> str:
    return "—" if v is None else f"{v:,.{d}f}"


# ---------------------------------------------------------------------------
# Compliance summary table
# ---------------------------------------------------------------------------
def compliance_rows(summary, lang: str = "en") -> List[Dict]:
    """One row per pollutant: hourly max, 8-hour max, daily average, the
    governing limit, the percentage of that limit reached, and a status.

    A single row per pollutant (rather than per averaging period) keeps the
    matrix to one page and lets a reviewer scan the whole survey at a glance;
    the per-period detail remains in the individual pollutant tables.
    """
    ar = lang == "ar"
    rows: List[Dict] = []
    for p in summary.pollutants:
        if p.is_supporting:
            continue
        periods = [e for e in p.period_evaluations
                   if e.averaging_period != "1 Year"]
        if not periods:
            continue

        # The governing limit is the one the data comes closest to.
        governing, ratio = None, -1.0
        for e in periods:
            v = e.max_value if e.max_value is not None else e.mean_value
            if e.limit_ugm3 and v is not None:
                r = v / e.limit_ugm3
                if r > ratio:
                    governing, ratio = e, r
        if governing is None:
            governing = periods[0]

        exceeded = any(e.verdict == "non-compliant" for e in periods)
        above = sum(e.exceedance_count for e in periods)
        insufficient = (p.hourly_capture_pct or 0) < 75

        if insufficient:
            status, verdict = "nr", ("غير قابل للإبلاغ" if ar else "NOT REPORTABLE")
        elif exceeded:
            status, verdict = "bad", ("تجاوز" if ar else "EXCEEDED")
        elif above:
            status, verdict = "warn", ("للعلم فقط" if ar else "SEE NOTE")
        else:
            status, verdict = "ok", ("مطابق" if ar else "COMPLIANT")

        r8 = _fmt(p.rolling_8h_max) if p.pollutant in ("CO", "O3") else "—"
        daily = next((e.mean_value for e in periods
                      if e.averaging_period == "24 Hour"), None)
        rows.append({
            "status": status,
            # Fill for the whole row, so an exceedance is shaded across the
            # full width rather than distinguished only by the word in the
            # final column.
            "row_fill": {"ok": "FFFFFF", "bad": "FDECEA",
                         "warn": "FFF7E6", "nr": "F3F4F6"}[status],
            "pollutant": DISPLAY.get(p.pollutant, p.pollutant),
            "hourly_max": _fmt(p.hourly_max),
            "rolling_8h": r8,
            "daily_avg": _fmt(daily if daily is not None else p.hourly_mean),
            "limit": (f"{_fmt(governing.limit_ugm3, 0)} "
                      f"({governing.averaging_period.replace(' (rolling)', '')})"
                      if governing.limit_ugm3 else "—"),
            "pct_of_limit": ("—" if ratio < 0 else f"{ratio * 100:,.0f}%"),
            "verdict": verdict,
        })
    return rows


def pollutant_verdict_line(p, lang: str = "en") -> str:
    """One-line finding printed in a callout beneath each pollutant section."""
    ar = lang == "ar"
    periods = [e for e in p.period_evaluations
               if e.averaging_period != "1 Year"]
    gov, ratio = None, -1.0
    for e in periods:
        v = e.max_value if e.max_value is not None else e.mean_value
        if e.limit_ugm3 and v is not None and v / e.limit_ugm3 > ratio:
            gov, ratio = e, v / e.limit_ugm3
    name = DISPLAY.get(p.pollutant, p.pollutant)
    if (p.hourly_capture_pct or 0) < 75:
        return (f"لم تبلغ نسبة التقاط بيانات {name} حد 75%؛ والنتائج غير قابلة للإبلاغ."
                if ar else
                f"Data capture for {name} did not meet the 75% requirement; "
                f"results are not reportable.")
    if any(e.verdict == "non-compliant" for e in periods):
        return (f"سُجلت تجاوزات لمعيار NCEC الخاص بـ {name}."
                if ar else
                f"Exceedance(s) of the NCEC standard for {name} were recorded.")
    if gov is None:
        return (f"لا يوجد حد معمول به لـ {name}؛ تُعرض النتائج كبيانات مساندة."
                if ar else
                f"No applicable NCEC limit for {name}; reported as supporting data.")
    v = gov.max_value if gov.max_value is not None else gov.mean_value
    per = gov.averaging_period.replace(" (rolling)", "")
    if ar:
        return (f"بلغت أعلى قيمة لـ {name} خلال فترة {per} مقدار {_fmt(v)} "
                f"ميكروغرام/م³ مقابل حد {_fmt(gov.limit_ugm3, 0)}، أي "
                f"{ratio * 100:,.0f}% من الحد المسموح به.")
    return (f"{per} maximum of {_fmt(v)} µg/m³ against a limit of "
            f"{_fmt(gov.limit_ugm3, 0)} µg/m³ — {ratio * 100:,.0f}% of the "
            f"permissible level.")


# ---------------------------------------------------------------------------
# Headline finding for the Executive Summary
# ---------------------------------------------------------------------------
def headline_finding(summary, lang: str = "en") -> str:
    ar = lang == "ar"
    evals = [e for p in summary.pollutants if not p.is_supporting
             for e in p.period_evaluations if e.averaging_period != "1 Year"]
    exceeded = sorted({p.pollutant for p in summary.pollutants
                       for e in p.period_evaluations
                       if e.verdict == "non-compliant"})
    # Values above a limit whose allowance spans a longer reference period than
    # the campaign are not a compliance failure, but they must still be stated.
    observed_above = sorted({p.pollutant for p in summary.pollutants
                             for e in p.period_evaluations
                             if e.averaging_period != "1 Year"
                             and e.exceedance_count > 0
                             and e.verdict != "non-compliant"})
    not_reportable = sorted({p.pollutant for p in summary.pollutants
                             if not p.is_supporting
                             and (p.hourly_capture_pct or 0) < 75})

    if exceeded:
        names = ", ".join(DISPLAY.get(x, x) for x in exceeded)
        head = (f"سُجلت تجاوزات لمعايير جودة الهواء المحيط الصادرة عن NCEC "
                f"لعام 2020 بالنسبة لـ {names} خلال فترة الرصد."
                if ar else
                f"Exceedances of the NCEC 2020 ambient air quality standards "
                f"were recorded for {names} during the survey period.")
    elif evals and not observed_above:
        head = ("لم تتجاوز جميع العناصر المرصودة الحدود المسموح بها في معايير "
                "جودة الهواء المحيط الصادرة عن NCEC لعام 2020 طوال فترة الرصد."
                if ar else
                "All monitored parameters complied with the NCEC 2020 ambient "
                "air quality standards throughout the survey period; no "
                "exceedances of the permissible limits were recorded.")
    elif evals:
        head = ("لم تُسجل تجاوزات للحدود المسموح بها وفق معايير جودة الهواء "
                "المحيط الصادرة عن NCEC لعام 2020 خلال فترة الرصد."
                if ar else
                "No exceedance of the permissible limits under the NCEC 2020 "
                "ambient air quality standards was recorded during the survey "
                "period.")
    else:
        head = ("لم تتوفر بيانات كافية لتقييم الامتثال."
                if ar else
                "Insufficient valid data was available to assess compliance.")

    if observed_above and not exceeded:
        names = ", ".join(DISPLAY.get(x, x) for x in observed_above)
        head += (f" وقد رُصدت قيم لـ {names} أعلى من مستوى التجاوز؛ وبما أن "
                 f"التجاوزات المسموح بها معرفة على فترة مرجعية أطول من مدة هذه "
                 f"الحملة، تُذكر هذه القيم لأغراض العلم فقط."
                 if ar else
                 f" Values above the exceedance level were recorded for "
                 f"{names}; as the applicable allowance is defined over a "
                 f"longer reference period than this survey, these are "
                 f"reported for information only.")

    if not_reportable:
        names = ", ".join(DISPLAY.get(x, x) for x in not_reportable)
        head += (f" ولم تبلغ نسبة التقاط البيانات لـ {names} الحد الأدنى "
                 f"البالغ 75%، وبالتالي فهي غير قابلة للإبلاغ."
                 if ar else
                 f" Data capture for {names} did not meet the 75% minimum "
                 f"requirement; these parameters are therefore reported as "
                 f"not reportable.")
    return head


# ---------------------------------------------------------------------------
# Recommendations, drafted from the results
# ---------------------------------------------------------------------------
def recommendations(campaign, summary, lang: str = "en") -> List[str]:
    ar = lang == "ar"
    out: List[str] = []

    exceeded = sorted({p.pollutant for p in summary.pollutants
                       for e in p.period_evaluations
                       if e.verdict == "non-compliant"})
    approaching = []
    for p in summary.pollutants:
        if p.is_supporting or p.hourly_max is None:
            continue
        for e in p.period_evaluations:
            if e.limit_ugm3 and e.max_value is not None:
                if 0.8 <= e.max_value / e.limit_ugm3 < 1.0:
                    approaching.append(DISPLAY.get(p.pollutant, p.pollutant))
                    break
    low_capture = sorted({DISPLAY.get(p.pollutant, p.pollutant)
                          for p in summary.pollutants if not p.is_supporting
                          and (p.hourly_capture_pct or 0) < 75})

    if exceeded:
        names = ", ".join(DISPLAY.get(x, x) for x in exceeded)
        out.append(
            f"يُوصى بالتحقيق في مصادر {names} في الموقع وتقييم إجراءات التحكم "
            f"المناسبة." if ar else
            f"Investigate the source(s) of {names} at the site and assess "
            f"appropriate control measures.")
        out.append(
            "يُوصى بإجراء رصد متابعة لتأكيد ما إذا كانت التجاوزات المسجلة "
            "تمثل ظرفاً عارضاً أم حالة مستمرة." if ar else
            "Undertake follow-up monitoring to establish whether the recorded "
            "exceedances represent a transient event or a sustained condition.")
    observed_above = sorted({DISPLAY.get(p.pollutant, p.pollutant)
                             for p in summary.pollutants
                             for e in p.period_evaluations
                             if e.averaging_period != "1 Year"
                             and e.exceedance_count > 0
                             and e.verdict != "non-compliant"})
    if observed_above and not exceeded:
        names = ", ".join(observed_above)
        out.append(
            f"رُصدت قيم لـ {names} أعلى من مستوى التجاوز وفق NCEC؛ ويُوصى "
            f"بالتحقق من مصادرها وبرصد أطول لتحديد ما إذا كان عدد التجاوزات "
            f"السنوي المسموح به عرضة للتجاوز." if ar else
            f"Values above the NCEC exceedance level were recorded for {names}. "
            f"Verification of the contributing sources, and monitoring over a "
            f"longer period, are recommended to establish whether the annual "
            f"allowance is likely to be exceeded.")

    if approaching:
        names = ", ".join(sorted(set(approaching)))
        out.append(
            f"بلغت تركيزات {names} ما يزيد على 80% من الحد المسموح به؛ ويُوصى "
            f"بمتابعتها في حملات الرصد اللاحقة." if ar else
            f"Concentrations of {names} reached more than 80% of the permissible "
            f"limit; continued attention to this parameter is recommended in "
            f"subsequent surveys.")
    if low_capture:
        names = ", ".join(low_capture)
        out.append(
            f"لم تبلغ نسبة التقاط البيانات لـ {names} حد 75%؛ ويُوصى بإعادة "
            f"الرصد لهذه العناصر للحصول على نتائج قابلة للإبلاغ." if ar else
            f"Data capture for {names} fell below the 75% requirement; repeat "
            f"monitoring of these parameters is recommended to obtain "
            f"reportable results.")

    days = max(round((summary.monitoring_hours or 0) / 24), 1)
    if days <= 7:
        out.append(
            f"تمثل هذه النتائج فترة رصد مدتها {days} يوم/أيام، وهي تعكس الظروف "
            f"السائدة خلال تلك الفترة فقط. ويُوصى بحملات رصد أطول أو موسمية "
            f"لتقييم الظروف النموذجية على مدار العام." if ar else
            f"These results represent a monitoring period of {days} day(s) and "
            f"characterise conditions prevailing during that period only. "
            f"Longer or seasonally repeated campaigns are recommended where "
            f"representative annual conditions are required.")

    out.append(
        "يُوصى بالاستمرار في برنامج الصيانة والمعايرة الدورية للأجهزة وفقاً "
        "لتوصيات الشركة المصنعة ومتطلبات USEPA." if ar else
        "Continue the routine instrument maintenance and calibration programme "
        "in accordance with the manufacturer's recommendations and USEPA "
        "requirements.")
    return out


# ---------------------------------------------------------------------------
# Limitations and reliance
# ---------------------------------------------------------------------------
def limitations(campaign, summary, lang: str = "en") -> List[str]:
    """Standard reliance wording. The provider should have this reviewed by
    their own advisers once before it is issued under their stamp."""
    ar = lang == "ar"
    client = campaign.client
    provider = campaign.provider
    if ar:
        return [
            f"أُعد هذا التقرير من قبل {provider} لصالح {client} حصراً، "
            f"وللغرض المذكور فيه فقط. ولا يجوز لأي طرف ثالث الاعتماد عليه دون "
            f"موافقة خطية مسبقة.",
            "تقتصر النتائج الواردة في هذا التقرير على الظروف السائدة في موقع "
            "الرصد خلال فترة الرصد المحددة، ولا تمثل بالضرورة الظروف في أوقات "
            "أو مواقع أخرى.",
            "تستند النتائج إلى البيانات التي جُمعت واعتُمدت وفقاً للإجراءات "
            "الموضحة في القسم 2.5. وقد استُبعدت البيانات غير الصالحة استناداً "
            "إلى مسوغ موثق.",
            "لا يتضمن هذا التقرير تقييماً لأثر المنشأة أو نمذجة للانتشار، ولا "
            "يشكل تقييماً للأثر البيئي.",
        ]
    return [
        f"This report has been prepared by {provider} for the exclusive use of "
        f"{client} and for the purpose stated herein. No third party may rely "
        f"upon it without prior written consent.",
        "The findings relate to conditions prevailing at the monitoring "
        "location during the stated survey period and are not necessarily "
        "representative of conditions at other times or locations.",
        "The results are based on data collected and validated in accordance "
        "with the procedures described in Section 2.5. Invalid data was "
        "excluded on the basis of documented justification.",
        "This report does not constitute an assessment of the facility's "
        "impact, a dispersion modelling study, or an Environmental Impact "
        "Assessment.",
    ]


def uncertainty_text(lang: str = "en") -> str:
    if lang == "ar":
        return ("عُوّرت أجهزة تحليل الغازات مقابل غازات مرجعية متتبعة دولياً. "
                "وبلغت شهادات المعايرة عدم يقين موسع قدره ±2% (k = 2، بمستوى "
                "ثقة يقارب 95%). وتنطبق قيمة عدم اليقين هذه على القيم "
                "الساعية المُبلغ عنها للملوثات الغازية.")
    return ("The gas analysers were calibrated against internationally "
            "traceable reference gases. The calibration certificates state an "
            "expanded uncertainty of " + DEFAULT_UNCERTAINTY + ". This "
            "uncertainty applies to the reported hourly values for the gaseous "
            "pollutants.")


# ---------------------------------------------------------------------------
# Site geometry — measurements only, no interpretation
# ---------------------------------------------------------------------------
def _bearing_km(lat1, lon1, lat2, lon2):
    """Initial bearing (degrees from true north) and great-circle distance."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    bearing = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    dist = 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return bearing, dist


def site_geometry_text(campaign, summary, lang: str = "en") -> Optional[str]:
    """State the station's position relative to the facility and the prevailing
    wind. Deliberately factual: no upwind/downwind conclusion is drawn."""
    flat = getattr(campaign, "facility_latitude", None)
    flon = getattr(campaign, "facility_longitude", None)
    if flat is None or flon is None:
        return None
    # bearing FROM the facility TO the station, i.e. where the station sits
    bearing, dist_km = _bearing_km(flat, flon, campaign.latitude,
                                   campaign.longitude)
    compass = COMPASS_16[int(round(bearing / 22.5)) % 16]
    dist = (f"{dist_km * 1000:,.0f} m" if dist_km < 1
            else f"{dist_km:,.1f} km")
    prevailing = summary.wind_rose.prevailing_direction
    if lang == "ar":
        ar_dist = (f"{dist_km * 1000:,.0f} متر" if dist_km < 1
                   else f"{dist_km:,.1f} كم")
        s = (f"يقع موقع الرصد على بعد {ar_dist} تقريباً في اتجاه {compass} "
             f"({bearing:.0f}° من الشمال الحقيقي) من المنشأة.")
        if prevailing:
            s += f" وكان اتجاه الرياح السائد خلال فترة الرصد {prevailing}."
        return s
    s = (f"The monitoring station was located approximately {dist} to the "
         f"{compass} ({bearing:.0f}° from true north) of the facility.")
    if prevailing:
        s += (f" The prevailing wind direction during the survey period was "
              f"from the {prevailing}.")
    return s
