# -*- coding: utf-8 -*-
"""Allocate report numbers.

A report number is a business identifier: it goes on the cover, into the
client's filing and into any dispute years later. Two documents sharing one is
a worse problem than a document missing one, so the number is never worked out
in the browser and never derived by counting what already exists — a count
repeats itself the moment a campaign is deleted, and two people creating
reports at the same second get the same answer. It comes from one counter that
the database increments atomically, so a number is handed out once and never
again.

It is allocated when the first report is generated, not when the campaign is
created, for two reasons:

* the date inside the number is the issue date, and a campaign is often set up
  weeks before its report is produced — numbering at creation would print a
  number whose own date contradicted the issue date beside it on the cover;
* not every campaign becomes a report. Test campaigns and abandoned jobs would
  each consume a number, leaving holes in the series. An auditor who sees 105,
  106, 109 asks what happened to 107.

Shape and starting point are configurable, because they are BSA's filing
convention rather than a technical decision:

    REPORT_NUMBER_PREFIX   default "BR-R"
    REPORT_NUMBER_START    default 105   (their manual series reached 104)
    REPORT_NUMBER_PAD      default 3     digits in the running number

producing, for a report issued on 6 August 2026: BR-R-060826-105
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

from pymongo import ReturnDocument

from db import db

log = logging.getLogger(__name__)

COUNTER_ID = "report_number"
PREFIX = os.environ.get("REPORT_NUMBER_PREFIX", "BR-R")
PAD = int(os.environ.get("REPORT_NUMBER_PAD", "3"))


def _start() -> int:
    try:
        return int(os.environ.get("REPORT_NUMBER_START", "105"))
    except ValueError:
        return 105


def _format(seq: int, when: datetime) -> str:
    return f"{PREFIX}-{when.strftime('%d%m%y')}-{seq:0{PAD}d}"


def has_number(value: Optional[str]) -> bool:
    """Whether a campaign already carries a real number.

    The context layer substitutes an em dash for a missing value, and that
    dash has been saved back onto campaigns in the past, so it is treated as
    absent rather than as a number.
    """
    return bool(value and value.strip() and value.strip() not in {"-", "—"})


async def _next_seq() -> int:
    """One number from the shared counter.

    The counter is seeded on first use rather than with ``$setOnInsert``:
    MongoDB rejects an update that both increments a field and sets it in the
    same operation, so the seed is a separate insert whose failure — because
    another worker seeded it first — is the expected case, not an error.
    """
    if await db.counters.find_one({"_id": COUNTER_ID}, {"_id": 1}) is None:
        try:
            await db.counters.insert_one(
                {"_id": COUNTER_ID, "seq": _start() - 1})
        except Exception:  # noqa: BLE001 — another worker got there first
            pass
    doc = await db.counters.find_one_and_update(
        {"_id": COUNTER_ID},
        {"$inc": {"seq": 1}},
        return_document=ReturnDocument.AFTER,
        upsert=True,
    )
    return int(doc["seq"])


async def ensure_report_number(campaign, campaign_id: str) -> Optional[str]:
    """Give the campaign a report number if it has none, and save it.

    Returns the number now on the campaign, or None if one could not be
    allocated. A failure here must never stop a report being produced: the
    document is still correct without a number, and a missing number is
    visible on the cover, whereas a report that failed to generate is not.
    """
    existing = getattr(campaign, "report_number", None)
    if has_number(existing):
        return existing

    # The date belongs to the issue, so the campaign's own reporting date wins
    # when it is set — that is what prints beside the number on the cover.
    when = getattr(campaign, "reporting_date", None) or datetime.now()
    if isinstance(when, str):
        try:
            when = datetime.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError:
            when = datetime.now()

    try:
        # A number typed by hand could already occupy the slot this counter
        # is about to reach, so each candidate is checked before it is used.
        for _ in range(25):
            number = _format(await _next_seq(), when)
            clash = await db.campaigns.find_one(
                {"report_number": number}, {"_id": 1})
            if clash is None:
                break
        else:
            log.warning("report numbering could not find a free number after "
                        "25 attempts — leaving the campaign unnumbered")
            return existing

        await db.campaigns.update_one(
            {"id": campaign_id}, {"$set": {"report_number": number}})
        try:
            campaign.report_number = number
        except Exception:  # noqa: BLE001 — frozen model, caller re-reads
            pass
        log.info("assigned report number %s to campaign %s",
                 number, campaign_id)
        return number
    except Exception:  # noqa: BLE001
        log.warning("report number allocation failed — the report is still "
                    "generated, without one", exc_info=True)
        return existing
