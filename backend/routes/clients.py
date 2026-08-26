"""Client records: create, edit, and link to campaigns.

Two things here beyond ordinary CRUD.

`/clients/suggestions` reads the client text already stored on every
campaign, groups the spellings, and matches each against the records that
exist. It is what turns "twenty-odd campaigns to link by hand" into a list
to confirm.

`/clients/{id}/campaigns` and the link endpoint are the only writes that
touch a campaign, and they touch one field. The client text a campaign
already carries is never altered: a report generated before and after
linking prints the same name unless someone deliberately changes it.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from audit import audit
from auth import current_username, require_admin
from client_models import (
    Client,
    ClientCreate,
    ClientSuggestion,
    ClientUpdate,
    normalise_name,
    utcnow,
)
from db import db, from_mongo, to_mongo

log = logging.getLogger(__name__)

router = APIRouter(prefix="/clients", tags=["clients"])


async def _all_clients() -> List[Client]:
    docs = await db.clients.find({}, {"_id": 0}).to_list(length=1000)
    return [Client(**d) for d in docs]


async def _counts() -> Counter:
    """Campaigns per linked client, counted from the campaigns themselves.

    Counted on read rather than stored. A number kept on the record would
    drift the first time a campaign was deleted through another route, and a
    wrong count is worse than a computed one.
    """
    docs = await db.campaigns.find({"client_id": {"$ne": None}},
                                   {"_id": 0, "client_id": 1}).to_list(2000)
    return Counter(d["client_id"] for d in docs if d.get("client_id"))


def _index(clients: List[Client]) -> Dict[str, Client]:
    """Every normalised spelling mapped to its client.

    Where two clients claim the same key the first is kept and the clash is
    logged: silently overwriting one would make a client unreachable by name
    with nothing to show why.
    """
    out: Dict[str, Client] = {}
    for c in clients:
        for key in c.match_keys():
            if key in out and out[key].id != c.id:
                log.warning("client name %r claimed by both %r and %r; "
                            "keeping the first", key, out[key].legal_name,
                            c.legal_name)
                continue
            out[key] = c
    return out


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@router.get("", response_model=List[Client])
async def list_clients(include_inactive: bool = False) -> List[Client]:
    clients = await _all_clients()
    counts = await _counts()
    for c in clients:
        c.campaign_count = counts.get(c.id, 0)
    if not include_inactive:
        clients = [c for c in clients if c.active]
    return sorted(clients, key=lambda c: c.display().lower())


@router.post("", response_model=Client, status_code=status.HTTP_201_CREATED)
async def create_client(payload: ClientCreate,
                        x_user: str = Depends(current_username)) -> Client:
    if not payload.legal_name.strip():
        raise HTTPException(status_code=400, detail="A legal name is required")
    existing = _index(await _all_clients())
    for key in payload.match_keys():
        clash = existing.get(key)
        if clash:
            raise HTTPException(
                status_code=409,
                detail=f"{clash.legal_name} already covers that name. Add the "
                       f"spelling to its list of aliases instead of creating a "
                       f"second record.")
    client = Client(**payload.model_dump(), created_by=x_user)
    await db.clients.insert_one(to_mongo(client.model_dump()))
    await audit("client.create", "client", client.id, x_user,
                {"legal_name": client.legal_name})
    return client


@router.get("/suggestions", response_model=List[ClientSuggestion])
async def suggestions() -> List[ClientSuggestion]:
    """Client spellings in the archive that are not yet linked to a record.

    Declared above `/{client_id}` so the literal path is matched first; a
    parameterised route registered earlier would swallow it.
    """
    docs = await db.campaigns.find(
        {}, {"_id": 0, "client": 1, "client_id": 1}).to_list(2000)
    unlinked = Counter(
        (d.get("client") or "").strip()
        for d in docs if not d.get("client_id") and (d.get("client") or "").strip()
    )
    index = _index(await _all_clients())
    out: List[ClientSuggestion] = []
    for text, count in unlinked.most_common():
        match = index.get(normalise_name(text))
        out.append(ClientSuggestion(
            client_text=text,
            campaign_count=count,
            suggested_client_id=match.id if match else None,
            suggested_client_name=match.display() if match else None,
        ))
    return out


@router.get("/{client_id}", response_model=Client)
async def get_client(client_id: str) -> Client:
    doc = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Client not found")
    client = Client(**doc)
    client.campaign_count = (await _counts()).get(client_id, 0)
    return client


@router.put("/{client_id}", response_model=Client)
async def update_client(client_id: str, payload: ClientUpdate,
                        x_user: str = Depends(current_username)) -> Client:
    doc = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Client not found")
    changes = {k: v for k, v in payload.model_dump(exclude_unset=True).items()
               if v is not None}
    if not changes:
        return Client(**doc)

    merged = Client(**{**doc, **changes})
    index = _index([c for c in await _all_clients() if c.id != client_id])
    for key in merged.match_keys():
        clash = index.get(key)
        if clash:
            raise HTTPException(
                status_code=409,
                detail=f"That name is already covered by {clash.legal_name}.")

    changes["updated_at"] = utcnow()
    await db.clients.update_one({"id": client_id}, {"$set": to_mongo(changes)})
    await audit("client.update", "client", client_id, x_user,
                {"fields": sorted(changes)})
    return Client(**{**doc, **changes})


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT,
               response_class=Response)
async def delete_client(client_id: str,
                        _admin: dict = Depends(require_admin),
                        x_user: str = Depends(current_username)) -> Response:
    """Remove a client that no campaign refers to.

    A client with campaigns is refused rather than cascaded. Deleting it
    would leave those campaigns pointing at a record that no longer exists,
    and the operator is better placed than the system to decide whether the
    right answer is to unlink them, merge them, or keep the record.
    """
    doc = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Client not found")
    linked = await db.campaigns.count_documents({"client_id": client_id})
    if linked:
        raise HTTPException(
            status_code=409,
            detail=f"{linked} campaign(s) are linked to this client. Unlink "
                   f"them first, or mark the client inactive to keep the "
                   f"record without it appearing in lists.")
    await db.clients.delete_one({"id": client_id})
    await audit("client.delete", "client", client_id, x_user,
                {"legal_name": doc.get("legal_name")})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Linking
# ---------------------------------------------------------------------------
class LinkRequest(BaseModel):
    client_id: Optional[str] = None
    # Where given, every campaign whose client text matches this one is
    # linked in the same action. Confirming twenty spellings one at a time is
    # what stops the archive ever getting tidied.
    apply_to_matching_text: Optional[str] = None


@router.get("/{client_id}/campaigns")
async def client_campaigns(client_id: str) -> List[Dict[str, Any]]:
    docs = await db.campaigns.find(
        {"client_id": client_id},
        {"_id": 0, "id": 1, "project_name": 1, "site_name": 1,
         "campaign_type": 1, "monitoring_start": 1, "monitoring_end": 1,
         "status": 1, "report_number": 1},
    ).sort("monitoring_start", -1).to_list(500)
    return [from_mongo(d) for d in docs]


@router.post("/link/{campaign_id}")
async def link_campaign(campaign_id: str, payload: LinkRequest,
                        x_user: str = Depends(current_username)
                        ) -> Dict[str, Any]:
    """Attach a campaign to a client record, or detach it.

    Only `client_id` is written. The `client` text stays exactly as typed, so
    a report generated after linking prints what it printed before unless
    someone changes it deliberately.
    """
    campaign = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if payload.client_id:
        client = await db.clients.find_one({"id": payload.client_id},
                                           {"_id": 0})
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

    targets = [campaign_id]
    if payload.apply_to_matching_text:
        same = await db.campaigns.find(
            {"client": payload.apply_to_matching_text, "client_id": None},
            {"_id": 0, "id": 1}).to_list(500)
        targets = sorted({campaign_id} | {d["id"] for d in same})

    await db.campaigns.update_many(
        {"id": {"$in": targets}},
        {"$set": to_mongo({"client_id": payload.client_id,
                           "updated_at": utcnow()})},
    )
    await audit("campaign.link_client", "campaign", campaign_id, x_user,
                {"client_id": payload.client_id, "campaigns": len(targets)})
    return {"linked": len(targets), "client_id": payload.client_id}


@router.post("/{client_id}/absorb")
async def absorb_spelling(client_id: str, payload: LinkRequest,
                          x_user: str = Depends(current_username)
                          ) -> Dict[str, Any]:
    """Adopt a spelling as an alias and link every campaign using it.

    The action the suggestions list is built for: one confirmation records
    the spelling on the client and links all the campaigns that use it, so a
    variant seen once is recognised from then on.
    """
    text = (payload.apply_to_matching_text or "").strip()
    if not text:
        raise HTTPException(status_code=400,
                            detail="No client spelling was given")
    doc = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Client not found")

    client = Client(**doc)
    if normalise_name(text) not in client.match_keys():
        aliases = list(client.aliases)
        if text not in aliases:
            aliases.append(text)
        await db.clients.update_one(
            {"id": client_id},
            {"$set": to_mongo({"aliases": aliases, "updated_at": utcnow()})})

    res = await db.campaigns.update_many(
        {"client": text, "client_id": None},
        {"$set": to_mongo({"client_id": client_id, "updated_at": utcnow()})},
    )
    await audit("client.absorb", "client", client_id, x_user,
                {"spelling": text, "campaigns": res.modified_count})
    return {"linked": res.modified_count, "alias": text}
