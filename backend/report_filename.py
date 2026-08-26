"""The name a report is saved under when someone downloads it.

Reports used to arrive as AAQ_Report_6516fb1d_v003_en_20260826_113712.docx.
Unique, and unreadable: in a folder of thirty, nothing on the name says whose
report it is, and the only thing distinguishing them is a timestamp.

The name now leads with the client, because that is how these files are
filed, searched and attached to an email. After it comes the report number,
which is what a client quotes back when they ask about one, then the
revision, so two revisions of the same report sit next to each other and
neither overwrites the other.

The project name is deliberately left out. It is usually a longer version of
something already in the report number's context, and including it produced
names past 120 characters, which Windows begins to struggle with once a
folder is nested a few levels deep.

Two names, not one. The file kept on the server keeps its existing unique
form so nothing already archived is renamed, moved or lost; this is only
what the browser is told to save it as.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

# What a report is of. Kept short: it sits between two long fields.
KIND_LABELS = {
    "air": "AAQ",
    "noise": "Noise",
    "soil": "Soil",
    "water": "Water",
    "sediment": "Sediment",
}

MAX_LENGTH = 110


def _slug(value: Optional[str], limit: int = 40) -> str:
    """Reduce a name to something every filesystem will accept.

    Windows rejects \\ / : * ? " < > | outright, and a name ending in a full
    stop or a space is silently mangled by Explorer. Accents are folded to
    ASCII so a name typed with them opens the same on a machine without the
    font.
    """
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s.-]", " ", text)
    text = re.sub(r"[\s_]+", "_", text).strip("._-")
    if len(text) > limit:
        # Cut on a word boundary where there is one within reach, so a name
        # is shortened rather than chopped mid-word.
        cut = text[:limit]
        if "_" in cut[limit // 2:]:
            cut = cut[:cut.rindex("_")]
        text = cut.strip("._-")
    return text


def report_filename(campaign, *, kind: str = "air", version: int = 1,
                    lang: str = "en", fmt: str = "docx",
                    client_name: Optional[str] = None) -> str:
    """The download name for one report version.

    `client_name` overrides the campaign's own text, so a campaign linked to
    a client record is saved under the recorded legal name rather than
    whatever was typed on the form.
    """
    client = _slug(client_name or getattr(campaign, "client", ""), 44)
    label = KIND_LABELS.get(kind, _slug(kind, 12) or "Report")

    number = _slug(getattr(campaign, "report_number", "") or "", 30)
    if not number:
        # A campaign that has not been numbered yet still needs a name that
        # cannot collide with the next report from the same campaign.
        number = f"v{version:03d}"

    revision = _slug(getattr(campaign, "revision", "") or "", 8)
    parts = [p for p in (client or "Report", label, number) if p]
    if revision:
        parts.append(f"Rev{revision}")
    # Arabic and English of the same revision are different documents and
    # must not overwrite each other in a downloads folder.
    if lang and lang != "en":
        parts.append(_slug(lang, 4))

    stem = "_".join(parts)
    if len(stem) > MAX_LENGTH:
        # Trim the client, never the report number: the number is what
        # identifies the document, and the client is the part a reader can
        # still recognise from a fragment.
        overflow = len(stem) - MAX_LENGTH
        client = client[:max(8, len(client) - overflow)].strip("._-")
        parts[0] = client or "Report"
        stem = "_".join(parts)

    return f"{stem}.{fmt}"
