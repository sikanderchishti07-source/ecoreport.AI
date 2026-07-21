# -*- coding: utf-8 -*-
"""Language tables for the dynamically generated sentences in context.py.

Everything the context builder composes at runtime (adaptive footnotes,
narratives, conclusions, dates) is templated here in both languages. Western
digits are used in both languages per the locked project decision.
"""

AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
             "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]

PERIOD_NAMES = {
    "en": {"1 Hour": "1 Hour", "24 Hour": "24 Hour",
           "8 Hour (rolling)": "8 Hour (rolling)", "1 Year": "1 Year"},
    "ar": {"1 Hour": "ساعة واحدة", "24 Hour": "24 ساعة",
           "8 Hour (rolling)": "8 ساعات (متحرك)", "1 Year": "سنة واحدة"},
}

PERIOD_ADJ = {  # adjective form used inside sentences
    "en": {"1 Hour": "hourly", "24 Hour": "daily", "8 Hour (rolling)": "8-hour"},
    "ar": {"1 Hour": "الساعية", "24 Hour": "اليومية",
           "8 Hour (rolling)": "لثماني ساعات"},
}

ALLOWANCE = {
    "en": {},  # pass-through
    "ar": {
        "24 times per year": "24 مرة في السنة",
        "3 times per annum": "3 مرات في السنة",
        "annual arithmetic mean; none allowed":
            "متوسط حسابي سنوي؛ غير مسموح بأي تجاوز",
        "1 time per annum": "مرة واحدة في السنة",
        "2 times in 30 days": "مرتان خلال 30 يوماً",
        "25 times per annum": "25 مرة في السنة",
        "None allowed": "غير مسموح بأي تجاوز",
        "None": "لا يوجد",
    },
}

POLLUTANT_NARRATIVE_NAMES = {
    "en": {
        "SO2": "Sulphur dioxide (SO2)", "NO2": "Nitrogen dioxide (NO2)",
        "CO": "Carbon Monoxide (CO)", "H2S": "Hydrogen sulfide (H2S)",
        "O3": "Ozone (O3)", "PM10": "Particulate Matter (PM10)",
        "PM25": "Particulate Matter (PM2.5)",
        "NOX_GROUP": "Oxides of Nitrogen (NO, NO2, NOx)",
        "PM_GROUP": "Particulate Matter (PM10 & PM2.5)",
    },
    "ar": {
        "SO2": "ثاني أكسيد الكبريت (SO2)", "NO2": "ثاني أكسيد النيتروجين (NO2)",
        "CO": "أول أكسيد الكربون (CO)", "H2S": "كبريتيد الهيدروجين (H2S)",
        "O3": "الأوزون (O3)", "PM10": "الجسيمات العالقة (PM10)",
        "PM25": "الجسيمات العالقة (PM2.5)",
        "NOX_GROUP": "أكاسيد النيتروجين (NO, NO2, NOx)",
        "PM_GROUP": "الجسيمات العالقة (PM10 و PM2.5)",
    },
}

FIG_REFS = {
    "en": {"a graph": "a graph", "graphs": "graphs", "tables": "the following tables"},
    "ar": {"a graph": "رسم بياني", "graphs": "رسوم بيانية",
           "tables": "الجداول التالية"},
}

CAPTURE_ROW_NAMES = {
    "en": {"temp": "Temp. (°C)", "rh": "Humidity (%)", "pressure": "Pressure (hPa)",
           "wd": "Wind Direction (°)", "ws": "Wind Speed (m/s)",
           "pollutant": "{sym} (µg/m³)"},
    "ar": {"temp": "درجة الحرارة (°م)", "rh": "الرطوبة (%)",
           "pressure": "الضغط (هكتوباسكال)", "wd": "اتجاه الرياح (°)",
           "ws": "سرعة الرياح (م/ث)", "pollutant": "{sym} (ميكروغرام/م³)"},
}

DYN = {
    "en": {
        "nr_footnote": ("*N/R: insufficient data — not reportable (data capture "
                        "below 75% for this averaging period)."),
        "fn_noncompliant": ("*Exceedance(s) of the NCEC standard were recorded "
                            "for the {periods} averaging period(s)."),
        "fn_clean": "*There were no exceedances of NCEC standards.",
        "fn_informational": (
            "*{n} value(s) above the NCEC exceedance level were observed; the "
            "applicable allowance is defined over a longer reference period than "
            "this monitoring campaign, so the count is reported for information "
            "only."),
        "cs_noncompliant": ("Accordingly, exceedances of the permissible limits "
                            "in NCEC {periods} standards were recorded."),
        "cs_clean": ("Accordingly, the results did not exceed the permissible "
                     "limits in NCEC {periods} standards."),
        "cs_informational": (
            "Values above the NCEC exceedance level were observed; the applicable "
            "allowance is defined over a longer reference period than this "
            "monitoring campaign and the observed count is therefore reported "
            "for information only."),
        "narrative": ("The recorded data of {name} was captured for {hours} hours "
                      "at the location. The results were summarized in the "
                      "following table, and represented on {figs} which includes "
                      "the maximum permissible limits in NCEC's 2020 ambient air "
                      "quality standards. "),
        "narrative_group_pm": (
            "The recorded data of {name} was captured for {hours} hours at the "
            "location. The results were summarized in the following tables, and "
            "represented on graphs which include the maximum permissible limits "
            "in NCEC's 2020 ambient air quality standards. "),
        "narrative_group_nox": (
            "The recorded data of {name} was captured for {hours} hours at the "
            "location. The results were summarized in the following table, and "
            "represented on graphs which include the maximum permissible limits "
            "in NCEC's 2020 ambient air quality standards. "),
        "nox_supporting": (" NO and NOx have no applicable NCEC limit and are "
                           "reported as supporting data only."),
        "capture_all_100": ("Hourly data capture rates are 100% for all the "
                            "monitored parameters at the location."),
        "capture_partial": (
            "The average hourly data capture rate across the monitored "
            "parameters at the location was {pct}%. Parameters below the 75% "
            "data-capture requirement are marked as not reportable in the "
            "relevant tables."),
        "concl_hmax": "The hourly maximum concentration was {v} µg/m³.",
        "concl_8hmax": " The 8-hour maximum concentration was {v} µg/m³.",
        "concl_exceed": "Exceedance(s) of NCEC standards were recorded.",
        "concl_clean": "There were no exceedances of NCEC standards.",
        "concl_informational": (
            "Observed values above the NCEC exceedance level are reported for "
            "information only (allowance reference period exceeds the campaign "
            "length)."),
        "concl_davg": "The daily average concentration was {v} µg/m³.",
        "met1": ("Hourly maximum and minimum temperatures were {mx} °C and "
                 "{mn} °C, respectively."),
        "met2": ("Hourly maximum and minimum relative humidity were {mx} % and "
                 "{mn} %, respectively."),
        "met3": ("Hourly maximum and minimum barometric pressure were {mx} hPa "
                 "and {mn} hPa, respectively."),
        "met4": ("The maximum and minimum hourly wind speed were {mx} m/s and "
                 "{mn} m/s, respectively."),
        "app1_none": ("No Data Exception due to the short period of monitoring "
                      "and all maintenance and multipoint calibration took place "
                      "before and after the monitoring time."),
        "app1_auto": ("{n} hourly record(s) contained negative pollutant values "
                      "that were invalidated at field level as "
                      "instrument/calibration artifacts"),
        "app1_manual": ("{n} hourly record(s) were manually invalidated during "
                        "data validation"),
        "app1_wrap": ("Data exceptions during the monitoring period: {parts}. "
                      "All remaining data were validated per the procedures in "
                      "Section 2.5."),
        "join_and": " & ",
        "join_semi": "; ",
        "window_to": "{a} to {b}",
        "dash": "—",
    },
    "ar": {
        "nr_footnote": ("*N/R: بيانات غير كافية — غير قابلة للإبلاغ (نسبة التقاط "
                        "البيانات أقل من 75% لفترة المتوسط هذه)."),
        "fn_noncompliant": ("*سُجلت تجاوزات لمعيار NCEC لفترة (فترات) المتوسط: "
                            "{periods}."),
        "fn_clean": "*لم تُسجل أي تجاوزات لمعايير NCEC.",
        "fn_informational": (
            "*رُصدت {n} قيمة (قيم) أعلى من مستوى التجاوز وفق NCEC؛ وبما أن "
            "التجاوزات المسموح بها معرفة على فترة مرجعية أطول من مدة حملة الرصد "
            "هذه، يُذكر هذا العدد لأغراض العلم فقط."),
        "cs_noncompliant": ("وبناءً على ذلك، سُجلت تجاوزات للحدود المسموح بها في "
                            "معايير NCEC {periods}."),
        "cs_clean": ("وبناءً على ذلك، لم تتجاوز النتائج الحدود المسموح بها في "
                     "معايير NCEC {periods}."),
        "cs_informational": (
            "رُصدت قيم أعلى من مستوى التجاوز وفق NCEC؛ وبما أن التجاوزات المسموح "
            "بها معرفة على فترة مرجعية أطول من مدة حملة الرصد هذه، يُذكر العدد "
            "المرصود لأغراض العلم فقط."),
        "narrative": ("التُقطت البيانات المسجلة لـ {name} لمدة {hours} ساعة في "
                      "الموقع. ولُخصت النتائج في الجدول التالي ومُثلت على {figs} "
                      "متضمنةً الحدود القصوى المسموح بها في معايير جودة الهواء "
                      "المحيط لعام 2020 الصادرة عن NCEC. "),
        "narrative_group_pm": (
            "التُقطت البيانات المسجلة لـ {name} لمدة {hours} ساعة في الموقع. "
            "ولُخصت النتائج في الجداول التالية ومُثلت على رسوم بيانية متضمنةً "
            "الحدود القصوى المسموح بها في معايير جودة الهواء المحيط لعام 2020 "
            "الصادرة عن NCEC. "),
        "narrative_group_nox": (
            "التُقطت البيانات المسجلة لـ {name} لمدة {hours} ساعة في الموقع. "
            "ولُخصت النتائج في الجدول التالي ومُثلت على رسوم بيانية متضمنةً "
            "الحدود القصوى المسموح بها في معايير جودة الهواء المحيط لعام 2020 "
            "الصادرة عن NCEC. "),
        "nox_supporting": (" لا يوجد حد معمول به لدى NCEC لكل من NO وNOx، وتُعرض "
                           "نتائجهما كبيانات مساندة فقط."),
        "capture_all_100": ("بلغت نسب التقاط البيانات الساعية 100% لجميع العناصر "
                            "المرصودة في الموقع."),
        "capture_partial": (
            "بلغ متوسط نسبة التقاط البيانات الساعية للعناصر المرصودة في الموقع "
            "{pct}%. وتُوسم العناصر التي تقل نسبتها عن متطلب 75% لالتقاط "
            "البيانات بأنها غير قابلة للإبلاغ في الجداول ذات الصلة."),
        "concl_hmax": "بلغ الحد الأقصى للتركيز الساعي {v} ميكروغرام/م³.",
        "concl_8hmax": " وبلغ الحد الأقصى لتركيز الثماني ساعات {v} ميكروغرام/م³.",
        "concl_exceed": "سُجلت تجاوزات لمعايير NCEC.",
        "concl_clean": "لم تُسجل أي تجاوزات لمعايير NCEC.",
        "concl_informational": (
            "تُعرض القيم المرصودة الأعلى من مستوى التجاوز وفق NCEC لأغراض العلم "
            "فقط (الفترة المرجعية للتجاوزات المسموح بها أطول من مدة الحملة)."),
        "concl_davg": "بلغ متوسط التركيز اليومي {v} ميكروغرام/م³.",
        "met1": ("بلغ الحدان الأقصى والأدنى لدرجة الحرارة الساعية {mx} °م و{mn} "
                 "°م على التوالي."),
        "met2": ("بلغ الحدان الأقصى والأدنى للرطوبة النسبية الساعية {mx} % و{mn} "
                 "% على التوالي."),
        "met3": ("بلغ الحدان الأقصى والأدنى للضغط الجوي الساعي {mx} هكتوباسكال "
                 "و{mn} هكتوباسكال على التوالي."),
        "met4": ("بلغ الحدان الأقصى والأدنى لسرعة الرياح الساعية {mx} م/ث و{mn} "
                 "م/ث على التوالي."),
        "app1_none": ("لا توجد استثناءات بيانات نظراً لقصر فترة الرصد، وقد أُجريت "
                      "جميع أعمال الصيانة والمعايرة متعددة النقاط قبل فترة الرصد "
                      "وبعدها."),
        "app1_auto": ("احتوى {n} سجل (سجلات) ساعي على قيم ملوثات سالبة استُبعدت "
                      "على مستوى الحقل باعتبارها آثاراً ناتجة عن الجهاز أو "
                      "المعايرة"),
        "app1_manual": ("استُبعد {n} سجل (سجلات) ساعي يدوياً أثناء اعتماد "
                        "البيانات"),
        "app1_wrap": ("استثناءات البيانات خلال فترة الرصد: {parts}. وقد اعتُمدت "
                      "جميع البيانات المتبقية وفق الإجراءات الواردة في القسم "
                      "2.5."),
        "join_and": " و",
        "join_semi": "؛ ",
        "window_to": "{a} إلى {b}",
        "dash": "—",
    },
}


def days_text(n: int, lang: str) -> str:
    if lang == "ar":
        if n == 1:
            return "يوم واحد"
        if n == 2:
            return "يومين"
        if 3 <= n <= 10:
            return f"{n} أيام"
        return f"{n} يوماً"
    return "one day" if n == 1 else f"{n} days"


def fmt_date(dt, lang: str, with_time: bool = False) -> str:
    """Long date, Western digits in both languages."""
    if lang == "ar":
        s = f"{dt.day} {AR_MONTHS[dt.month - 1]} {dt.year}"
        if with_time:
            h12 = dt.hour % 12 or 12
            ampm = "ص" if dt.hour < 12 else "م"
            s += f"، {h12}:{dt.minute:02d} {ampm}"
        return s
    if with_time:
        return dt.strftime("%B %d, %Y, %I:%M %p").replace(" 0", " ")
    return dt.strftime("%B %d, %Y")
