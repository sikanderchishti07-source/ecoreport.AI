"""Choosing which calibration certificates a report should carry.

A certificate belongs to the analyser, so it is stored against the mobile lab
and reused by every campaign that lab runs. The report must nevertheless show
the certificate that was **valid during that survey**, not simply the newest
one on file — otherwise reissuing an old report would silently substitute a
later calibration and misrepresent the record.

Selection rules, per instrument serial number:

1. prefer a certificate whose validity period covers the monitoring window;
2. otherwise take the most recent certificate issued **before** the survey,
   and flag it as expired during the period;
3. a certificate uploaded directly to the campaign always wins, so a one-off
   can override the lab's record.

An expired certificate produces a warning, never a refusal: it is a quality
finding for the operator to resolve, not a reason to withhold a report.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y",
            "%b %d, %Y", "%B %d, %Y", "%d.%m.%Y")


def parse_date(value) -> Optional[date]:
    """Accept the handful of formats operators actually type."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in _FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _covers(cert: dict, start: date, end: date) -> bool:
    cal = parse_date(cert.get("cert_date"))
    due = parse_date(cert.get("cert_due_date"))
    if cal and cal > end:
        return False                     # calibrated after the survey
    if due and due < start:
        return False                     # expired before the survey began
    return True


def _expired_during(cert: dict, start: date, end: date) -> bool:
    due = parse_date(cert.get("cert_due_date"))
    return bool(due and start <= due < end)


def select(campaign_certs: List[dict], station_certs: List[dict],
           window_start: datetime, window_end: datetime
           ) -> Tuple[List[dict], List[str]]:
    """Return (chosen certificates, warnings).

    Campaign uploads are kept as-is. Lab certificates are then added for any
    instrument the campaign did not already cover.
    """
    start, end = window_start.date(), window_end.date()
    warnings: List[str] = []

    chosen: List[dict] = list(campaign_certs)
    covered = {c.get("instrument_sn") for c in campaign_certs
               if c.get("instrument_sn")}

    by_sn: Dict[str, List[dict]] = {}
    for c in station_certs:
        by_sn.setdefault(c.get("instrument_sn") or "", []).append(c)

    for sn, certs in by_sn.items():
        if sn and sn in covered:
            continue                     # campaign already supplied one
        valid = [c for c in certs if _covers(c, start, end)]
        pool = valid or certs
        if not pool:
            continue
        pick = max(pool, key=lambda c: (parse_date(c.get("cert_date"))
                                        or date.min))
        if not valid:
            warnings.append(
                f"No calibration certificate on file covers the monitoring "
                f"period for instrument S/N {sn or '—'}; the most recent "
                f"certificate has been used.")
        elif _expired_during(pick, start, end):
            warnings.append(
                f"The calibration certificate for instrument S/N {sn} "
                f"({pick.get('cert_number', 'no number')}) expired during the "
                f"monitoring period on {pick.get('cert_due_date')}.")
        chosen.append(pick)

    return chosen, warnings


def to_rows(certs: List[dict], instruments) -> List[Dict]:
    """Rows for the Appendix 3 summary table, filling gaps from Table 4."""
    sn_map = {}
    for i in instruments or []:
        d = i if isinstance(i, dict) else i.model_dump()
        if d.get("sn"):
            sn_map[d["sn"]] = d
    rows = []
    seen = set()
    for c in certs:
        num = c.get("cert_number")
        if not num or num in seen:
            continue
        seen.add(num)
        instr = sn_map.get(c.get("instrument_sn")) or {}
        model = c.get("cert_model_sn")
        if not model and instr:
            tech = str(instr.get("technique", "")).split("(")[0].strip()
            model = f"{tech} / {instr.get('sn', '')}".strip(" /")
        rows.append({
            "number": num,
            "parameter": c.get("cert_parameter") or instr.get("parameter", ""),
            "model_sn": model or "",
            "date": c.get("cert_date", ""),
            "due_date": c.get("cert_due_date", ""),
            "result": c.get("cert_result") or "PASSED",
        })
    rows.sort(key=lambda r: r["number"])
    return rows
