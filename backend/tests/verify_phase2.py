"""Standalone verification of EcoReport Phase 2 calc engine against the locked spec.
Runs calc.py directly with synthetic readings — no MongoDB required.
"""
import sys
sys.path.insert(0, "/home/claude/ecoreport/backend")

from datetime import datetime, timedelta, timezone, date
from models import Campaign, Reading, PollutantLimit, AllowanceRule, AllowanceWindow, INSUFFICIENT_STR
from db import NCEC_LIMITS  # seed values (import triggers env vars — patch first)

import calc

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("PASS" if cond else "FAIL") + f"  {name}" + (f"  [{detail}]" if detail and not cond else ""))

UTC = timezone.utc
START = datetime(2026, 3, 1, 0, 0, tzinfo=UTC)

def mk_campaign(hours):
    return Campaign(
        project_name="T", client="C", site_name="S", latitude=24.7, longitude=46.7,
        monitoring_start=START, monitoring_end=START + timedelta(hours=hours),
    )

def mk_readings(hours, **series):
    """series: field -> list of values (None allowed) or constant."""
    out = []
    for i in range(hours):
        kw = {"campaign_id": "x", "timestamp": START + timedelta(hours=i)}
        for f, v in series.items():
            kw[f] = v[i] if isinstance(v, list) else v
        out.append(Reading(**kw))
    return out

def limits_obj():
    return [PollutantLimit(**row) for row in NCEC_LIMITS]

LIMS = limits_obj()
def lim(pol, period):
    return next(l for l in LIMS if l.pollutant == pol and l.averaging_period == period)

# ---------------------------------------------------------------- 1. rolling 8h
r = mk_readings(24, CO=[float(i) for i in range(24)])
roll = calc.rolling_8h(r, "CO")
check("8h rolling: first 7 hours blank", all(v is None for v in roll[:7]) and roll[7] is not None)
check("8h rolling: value at i=7 == mean(0..7)=3.5", abs(roll[7] - 3.5) < 1e-9, f"got {roll[7]}")

# 6-of-8 validity rule
vals = [float(i) for i in range(24)]
for j in (10, 11, 12):  # 3 invalid in window ending at 12..14
    vals[j] = None
r = mk_readings(24, CO=vals)
roll = calc.rolling_8h(r, "CO")
# window ending at i=12 covers 5..12, has 3 Nones -> 5 valid -> blank
check("8h rolling: <6 valid in window -> blank", roll[12] is None)
# window ending at i=17 covers 10..17, has 3 Nones -> 5 valid -> blank; i=18 covers 11..18 -> 2 Nones -> 6 valid -> value
check("8h rolling: exactly 6 valid -> value", roll[18] is not None)

# ---------------------------------------------------------------- 2. daily means 75% gate
vals = [10.0]*24
for j in range(7):  # 7 missing -> 17/24 = 70.8% -> below 75
    vals[j] = None
r = mk_readings(24, SO2=vals)
dm = calc.daily_means(r, "SO2")
check("daily mean: <75% of day's rows -> None", dm[0][1] is None, str(dm[0]))
vals = [10.0]*24
for j in range(6):  # 18/24 = 75% -> passes
    vals[j] = None
r = mk_readings(24, SO2=vals)
dm = calc.daily_means(r, "SO2")
check("daily mean: exactly 75% -> computed", dm[0][1] == 10.0, str(dm[0]))

# KNOWN-ISSUE probe: day with rows entirely MISSING (not null values)
r_full = mk_readings(24, SO2=10.0)
r_sparse = r_full[:10]  # only 10 rows exist for the day
dm = calc.daily_means(r_sparse, "SO2")
print(f"  [probe] day with only 10 of 24 rows present: expected={dm[0][3]}, mean={dm[0][1]}"
      f"  -> denominator is rows-present, NOT hours-in-window")

# ---------------------------------------------------------------- 3. negative auto-flag (ingest simulation)
# Ingest nulls the field; calc treats as missing. Simulate post-ingest state:
r = mk_readings(100, SO2=[None if i < 30 else 50.0 for i in range(100)], Temp=-5.0)
c = mk_campaign(100)
summ = calc.build_campaign_summary(c, r, LIMS)
so2 = next(p for p in summ.pollutants if p.pollutant == "SO2")
check("field-level invalidation: SO2 capture 70% -> hourly stats suppressed",
      so2.hourly_capture_pct == 70.0 and so2.hourly_max is None)
check("met exempt: negative Temp still used", summ.meteorology.temp_mean == -5.0)

# ---------------------------------------------------------------- 4. 75% gate + verdict taxonomy on a 14-day campaign
HOURS = 336
c = mk_campaign(HOURS)

# Clean data, no exceedances
r = mk_readings(HOURS, SO2=50.0, NO2=40.0, CO=500.0, H2S=1.0, O3=60.0,
                PM10=80.0, PM25=12.0, NO=5.0, NOx=45.0,
                WindSpeed=3.0, WindDirection=270.0, Temp=25.0, RH=40.0, Pressure=1010.0)
summ = calc.build_campaign_summary(c, r, LIMS)
P = {p.pollutant: p for p in summ.pollutants}

def pe(pol, period):
    return next(e for e in P[pol].period_evaluations if e.averaging_period == period)

# H2S zero-tolerance -> evaluable on short campaign
check("H2S 1hr (zero-tolerance): verdict=compliant on 14-day campaign",
      pe("H2S", "1 Hour").verdict == "compliant")
check("H2S 24hr (zero-tolerance): verdict=compliant", pe("H2S", "24 Hour").verdict == "compliant")

# Annual-allowance limits with 0 observed exceedances -> insufficient (window not covered)
check("SO2 1hr (24/yr allowance): 0 exceed -> insufficient on short campaign",
      pe("SO2", "1 Hour").verdict == INSUFFICIENT_STR, pe("SO2", "1 Hour").verdict)
check("NO2 1hr (24/yr): insufficient", pe("NO2", "1 Hour").verdict == INSUFFICIENT_STR)
check("PM10 24hr (24/yr): insufficient", pe("PM10", "24 Hour").verdict == INSUFFICIENT_STR)
check("CO 8hr (2/30d): insufficient on 14-day campaign",
      pe("CO", "8 Hour (rolling)").verdict == INSUFFICIENT_STR, pe("CO", "8 Hour (rolling)").verdict)
check("O3 8hr (25/yr): insufficient", pe("O3", "8 Hour (rolling)").verdict == INSUFFICIENT_STR)

# exceedance count still reported as informational
check("informational exceedance count present even when not evaluable",
      pe("SO2", "1 Hour").exceedance_count == 0 and pe("SO2", "1 Hour").exceedance_evaluable is False)

# Annual rows always present & insufficient
check("SO2 1yr row exists and is insufficient",
      pe("SO2", "1 Year").verdict == INSUFFICIENT_STR)
check("PM25 1yr row exists and is insufficient",
      pe("PM25", "1 Year").verdict == INSUFFICIENT_STR)

# NO/NOx: supporting only
check("NO has no period evaluations", P["NO"].is_supporting and P["NO"].period_evaluations == [])
check("NOx has no period evaluations", P["NOx"].is_supporting and P["NOx"].period_evaluations == [])
check("NO hourly stats still computed", P["NO"].hourly_mean == 5.0)

# ---------------------------------------------------------------- 5. exceedance -> direct non-compliance
# H2S spike -> zero-tolerance violated
vals = [1.0]*HOURS; vals[50] = 20.0  # > 14
r2 = mk_readings(HOURS, H2S=vals)
summ2 = calc.build_campaign_summary(c, r2, LIMS)
h2s = next(p for p in summ2.pollutants if p.pollutant == "H2S")
e1 = next(e for e in h2s.period_evaluations if e.averaging_period == "1 Hour")
check("H2S single exceedance -> non-compliant", e1.verdict == "non-compliant", e1.verdict)

# SO2: 25 hourly exceedances > 24/yr allowance -> direct non-compliance even short campaign
vals = [50.0]*HOURS
for i in range(25): vals[i] = 500.0  # > 441
r3 = mk_readings(HOURS, SO2=vals)
summ3 = calc.build_campaign_summary(c, r3, LIMS)
so2 = next(p for p in summ3.pollutants if p.pollutant == "SO2")
e1 = next(e for e in so2.period_evaluations if e.averaging_period == "1 Hour")
check("SO2 25 observed > 24/yr allowance -> non-compliant (direct evidence)",
      e1.verdict == "non-compliant", e1.verdict)
# and 24 observed -> back to insufficient (can't prove compliance)
vals = [50.0]*HOURS
for i in range(24): vals[i] = 500.0
r4 = mk_readings(HOURS, SO2=vals)
summ4 = calc.build_campaign_summary(c, r4, LIMS)
so2 = next(p for p in summ4.pollutants if p.pollutant == "SO2")
e1 = next(e for e in so2.period_evaluations if e.averaging_period == "1 Hour")
check("SO2 24 observed = allowance -> insufficient (not provable either way)",
      e1.verdict == INSUFFICIENT_STR, e1.verdict)

# ---------------------------------------------------------------- 6. row-level manual flag kills all fields
r5 = mk_readings(100, SO2=50.0, Temp=25.0)
for i in range(50):
    r5[i].valid = False
c100 = mk_campaign(100)
summ5 = calc.build_campaign_summary(c100, r5, LIMS)
so2 = next(p for p in summ5.pollutants if p.pollutant == "SO2")
check("manual row flag: SO2 capture drops to 50%", so2.hourly_capture_pct == 50.0)
check("manual row flag also removes met fields", summ5.meteorology.temp_capture_pct == 50.0)

# ---------------------------------------------------------------- 7. wind rose
ws = [1.0]*50 + [3.0]*30 + [5.0]*20     # calm / mid / high
wd = [0.0]*60 + [180.0]*40              # N x60, S x40
r6 = mk_readings(100, WindSpeed=ws, WindDirection=wd)
summ6 = calc.build_campaign_summary(c100, r6, LIMS)
wr = summ6.wind_rose
check("wind rose: prevailing = N", wr.prevailing_direction == "N", str(wr.prevailing_direction))
check("wind rose: calms = 50 (WS<2.10)", wr.calms_count == 50, str(wr.calms_count))
check("wind rose: calms_pct = 50%", abs(wr.calms_pct - 50.0) < 1e-9)
n_row = next(x for x in wr.direction_rows if x.direction == "N")
check("wind rose: N total = 60", n_row.total == 60, str(n_row.total))
check("wind rose: bin boundary [min,max): ws=2.10 not calm",
      calc._speed_class(2.10, c100.wind_rose_bins) == "2.10-3.60")
check("compass: 348.75 -> N boundary handling", calc._compass_bin(348.75) in ("N", "NNW"))
check("compass: 11.24 -> N", calc._compass_bin(11.24) == "N")
check("compass: 11.26 -> NNE", calc._compass_bin(11.26) == "NNE")

# ---------------------------------------------------------------- 8. KNOWN-ISSUE probe: rolling window is index-based
# Remove rows 8..15 entirely (gap), keep the rest. Rolling at what was hour 16
# now averages across an 8-clock-hour+gap span.
r7full = mk_readings(24, CO=[float(i) for i in range(24)])
r7 = r7full[:8] + r7full[16:]
roll7 = calc.rolling_8h(r7, "CO")
i16 = 8  # index of the reading stamped hour 16
print(f"  [probe] index-based rolling across an 8-hour data gap: value at ts=16h is "
      f"{roll7[15-8+8] if len(roll7)>15 else roll7[-1]} (window mixes hours 1..7 with 16.. -> spans 16 clock-hours)")

# ---------------------------------------------------------------- 9. NCEC seed values vs user's Table 5
expected = {
    ("SO2","1 Hour"):441, ("SO2","24 Hour"):217, ("SO2","1 Year"):65,
    ("CO","1 Hour"):40000, ("CO","8 Hour (rolling)"):10000,
    ("O3","8 Hour (rolling)"):157,
    ("H2S","1 Hour"):14, ("H2S","24 Hour"):4,
    ("NO2","1 Hour"):200, ("NO2","1 Year"):100,
    ("PM10","24 Hour"):340, ("PM10","1 Year"):50,
    ("PM25","24 Hour"):35, ("PM25","1 Year"):15,
}
seeded = {(l.pollutant, l.averaging_period): l.limit_ugm3 for l in LIMS}
check("NCEC seed matches Table 5 exactly (14 rows)", seeded == expected,
      str({k: (seeded.get(k), v) for k, v in expected.items() if seeded.get(k) != v}))

# ---------------------------------------------------------------- summary
print(f"\n{'='*60}\n{len(PASS)} passed, {len(FAIL)} failed")
for name, d in FAIL:
    print(f"  FAILED: {name} {d}")

# ================================================================ POST-FIX REGRESSION CHECKS
print("\n--- post-fix regression checks ---")
PASS2, FAIL2 = [], []
def check2(name, cond, detail=""):
    (PASS2 if cond else FAIL2).append((name, detail))
    print(("PASS" if cond else "FAIL") + f"  {name}" + (f"  [{detail}]" if detail and not cond else ""))

# A) daily denominator now prorated to hours-in-window (missing ROWS count against capture)
c24 = mk_campaign(24)
r_sparse = mk_readings(24, SO2=10.0)[:10]   # only 10 of 24 hourly rows exist
s = calc.build_campaign_summary(c24, r_sparse, LIMS)
so2 = next(p for p in s.pollutants if p.pollutant == "SO2")
e24 = next(e for e in so2.period_evaluations if e.averaging_period == "24 Hour")
check2("daily: 10 rows present of 24 window-hours -> day invalid (41.7% < 75%)",
       e24.valid_readings == 0 and e24.capture_pct == 0.0,
       f"valid_days={e24.valid_readings} cap={e24.capture_pct}")

# partial-day proration still honored: 12-hour window, 10 rows -> 10/12 = 83% -> valid day
c12 = mk_campaign(12)
r10 = mk_readings(12, SO2=10.0)[:10]
s = calc.build_campaign_summary(c12, r10, LIMS)
so2 = next(p for p in s.pollutants if p.pollutant == "SO2")
e24 = next(e for e in so2.period_evaluations if e.averaging_period == "24 Hour")
check2("daily: partial first/last day prorated (10 of 12 window-hours -> valid)",
       e24.valid_readings == 1, f"valid_days={e24.valid_readings}")

# B) rolling window is clock-hour based across gaps
r7full = mk_readings(24, CO=[float(i) for i in range(24)])
r7 = r7full[:8] + r7full[16:]   # hours 8..15 missing entirely
roll7 = calc.rolling_8h(r7, "CO")
# reading stamped hour 16: clock window 9..16 has only hours 16 present -> 1 valid -> blank
i_h16 = 8
check2("rolling: 8h data gap -> window has <6 clock-hour slots -> blank",
       roll7[i_h16] is None, f"got {roll7[i_h16]}")
# reading stamped hour 23: clock window 16..23, all 8 present -> mean(16..23)=19.5
check2("rolling: recovers once 8 contiguous clock hours exist again",
       roll7[-1] == 19.5, f"got {roll7[-1]}")

# C) "first 7 hours of the monitoring window" blank even if early rows missing
r_late = mk_readings(24, CO=100.0)[3:]  # first row stamped hour 3
roll = calc.rolling_8h(r_late, "CO", window_start=START)
# reading at hour 7 is index 4; window covers campaign hours 0..7 but 0..2 missing -> 5 valid -> blank
check2("rolling: anchored to window start (hour-7 value blank when hours 0-2 missing)",
       roll[4] is None)
check2("rolling: hour-10 value present (window 3..10 fully valid)", roll[7] == 100.0)

# D) out-of-window readings excluded; capture can't exceed 100%
r_extra = mk_readings(25, SO2=10.0)  # 25 rows incl. trailing endpoint row at end-of-window
c24b = mk_campaign(24)
s = calc.build_campaign_summary(c24b, r_extra, LIMS)
so2 = next(p for p in s.pollutants if p.pollutant == "SO2")
check2("window filter: trailing endpoint row dropped -> capture exactly 100%",
       so2.hourly_capture_pct == 100.0 and so2.hourly_valid_count == 24,
       f"cap={so2.hourly_capture_pct} n={so2.hourly_valid_count}")

# E) full original spec suite still green after patch (rerun key invariants)
c336 = mk_campaign(336)
r336 = mk_readings(336, SO2=50.0, H2S=1.0, CO=500.0, O3=60.0, NO2=40.0, PM10=80.0, PM25=12.0)
s = calc.build_campaign_summary(c336, r336, LIMS)
Pm = {p.pollutant: p for p in s.pollutants}
def pe2(pol, per): return next(e for e in Pm[pol].period_evaluations if e.averaging_period == per)
check2("spec invariants hold post-fix: H2S compliant / SO2-1hr insufficient / 1yr insufficient",
       pe2("H2S","1 Hour").verdict == "compliant"
       and pe2("SO2","1 Hour").verdict == INSUFFICIENT_STR
       and pe2("SO2","1 Year").verdict == INSUFFICIENT_STR)
check2("8h rolling stats still populated for CO on clean data",
       Pm["CO"].rolling_8h_mean == 500.0 and Pm["CO"].rolling_8h_expected_count == 329)

print(f"\n{len(PASS2)} post-fix checks passed, {len(FAIL2)} failed")
for n, d in FAIL2: print(f"  FAILED: {n} {d}")
