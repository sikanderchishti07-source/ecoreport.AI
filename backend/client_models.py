"""Client records.

Until now a client was free text typed fresh on every campaign, and the
archive shows what that costs: SAJCO, saico private and SAJCO QIDDIYAH are
one company written three ways, so no report, invoice or search treats them
as the same customer.

A record fixes more than tidiness. It gives one legal name that prints
identically on every report, one place for the contact a share link is sent
to, and one place for the reporting defaults a client's work always uses.

Kept deliberately additive. A campaign gains an optional `client_id`
alongside the `client` text it already stores, exactly as `gas_units_map`
was added beside `gas_units`. Nothing is migrated, nothing is required, and
an unlinked campaign prints its text as it always has. A feature that
cannot break the archive is a feature that can be switched off.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalise_name(value: str) -> str:
    """Fold a client name to a comparable key.

    Case, punctuation, repeated whitespace and the corporate suffixes that
    come and go between one campaign form and the next are all noise:
    "SAJCO Contracting Co. Ltd." and "sajco contracting company" are the
    same customer. What survives is the distinguishing part of the name.

    Deliberately not fuzzy. Two genuinely different companies must never
    fold together — an invoice or a report sent to the wrong client is a
    worse outcome than a duplicate record — so this only removes noise it
    can name, and never guesses at closeness.
    """
    if not value:
        return ""
    text = re.sub(r"[^\w\s]", " ", str(value).lower())
    text = " ".join(text.split())
    # Stripped from the end, repeatedly, longest first. "Contracting Co. Ltd."
    # sheds three words and has to shed them in order; matching the shortest
    # first would strip "co" and leave "ltd" stranded.
    suffixes = sorted((
        "company limited", "and sons", "co ltd", "company", "limited",
        "corporation", "establishment", "contracting", "holdings", "trading",
        "holding", "private", "group", "corp", "llc", "inc", "est", "pvt",
        "ltd", "co",
    ), key=len, reverse=True)
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if text.endswith(" " + suffix):
                text = text[: -(len(suffix) + 1)].strip()
                changed = True
                break
        # Stripping "Contracting Company" off "Haif Trading And Contracting
        # Company" leaves a dangling connective. It carries no meaning at the
        # end of a name, so it goes too, and the loop runs again.
        for tail in ("and", "&", "for", "of"):
            if text.endswith(" " + tail):
                text = text[: -(len(tail) + 1)].strip()
                changed = True
    # A name that is nothing but suffixes keeps its original words: folding
    # "Trading Company" to an empty string would match it against every other
    # client whose name also reduced to nothing.
    return text or " ".join(re.sub(r"[^\w\s]", " ", str(value).lower()).split())


class ClientBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # The name as it should appear on an issued report. Held apart from the
    # short name because a report carries the legal entity while a screen
    # carries whatever fits in a column.
    legal_name: str
    short_name: Optional[str] = None

    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None

    # Spellings already present in the archive. Kept so the campaigns typed
    # before this existed can be recognised and offered for linking, rather
    # than retyped.
    aliases: List[str] = Field(default_factory=list)

    notes: Optional[str] = None
    active: bool = True

    def display(self) -> str:
        return self.short_name or self.legal_name

    def match_keys(self) -> List[str]:
        """Every normalised form this client should be recognised by."""
        seen: List[str] = []
        for raw in [self.legal_name, self.short_name, *self.aliases]:
            key = normalise_name(raw or "")
            if key and key not in seen:
                seen.append(key)
        return seen


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    legal_name: Optional[str] = None
    short_name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    aliases: Optional[List[str]] = None
    notes: Optional[str] = None
    active: Optional[bool] = None


class Client(ClientBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    created_by: Optional[str] = None
    # Filled by the API when listing, never stored: a count that lived in the
    # record would drift the moment a campaign was deleted somewhere else.
    campaign_count: int = 0


class ClientSuggestion(BaseModel):
    """An unlinked spelling in the archive, and the record it likely means."""
    client_text: str
    campaign_count: int
    suggested_client_id: Optional[str] = None
    suggested_client_name: Optional[str] = None
