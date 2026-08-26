"""EcoReport AI — FastAPI backend entrypoint (Phase 1 skeleton)."""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

# Started before the routers are imported. An exception raised while a module
# is loading is precisely the kind that leaves nothing behind, and reporting
# has to already be running to catch it. Without a SENTRY_DSN this is a no-op.
from sentry_setup import init_sentry, note_user

init_sentry()

from db import create_indexes, seed_pollutant_limits
from auth import current_user
from routes import auth_routes as auth_router
from routes import campaigns as campaigns_router
from routes import clients as clients_router
from routes import limits as limits_router
from routes import readings as readings_router
from routes import history as history_router
from routes import media as media_router
from routes import samples as samples_router
from routes import lab_samples as lab_samples_router
from routes import noise as noise_router
from routes import portal as portal_router
from routes import report as report_router
from routes import review as review_router
from routes import summary as summary_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("ecoreport")

app = FastAPI(title="EcoReport AI", version="0.1.0")

api = APIRouter(prefix="/api")


@api.get("/")
async def root() -> dict:
    return {"service": "EcoReport AI", "phase": "1", "status": "ok"}


@api.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# Mount domain routers under /api
from fastapi import Depends as _Depends

api.include_router(auth_router.router)  # open: setup/login


async def _signed_in(user: dict = _Depends(current_user)) -> dict:
    """Resolve the signed-in user and tag any error that follows with it.

    Wrapped here rather than changing auth.py: the authentication itself is
    unchanged, and every protected router already depends on it, so one
    wrapper covers the whole application. A username only — enough to ask the
    person what they were doing, and nothing more.
    """
    note_user(user.get("name"))
    return user


_protected = [_Depends(_signed_in)]
api.include_router(campaigns_router.router, dependencies=_protected)
api.include_router(clients_router.router, dependencies=_protected)
api.include_router(readings_router.router, dependencies=_protected)
api.include_router(limits_router.router, dependencies=_protected)
api.include_router(summary_router.router, dependencies=_protected)
api.include_router(report_router.router, dependencies=_protected)
api.include_router(review_router.router, dependencies=_protected)
api.include_router(history_router.router, dependencies=_protected)
api.include_router(media_router.router, dependencies=_protected)
# Water and soil samples: recorded on site, read by nothing yet.
api.include_router(samples_router.router, dependencies=_protected)
# Soil and water reporting: parameter profiles, laboratory samples, the
# results grid and the evaluated matrix. Distinct from samples_router above,
# which records what the field operator captures during a visit; this one
# holds what the laboratory reports afterwards.
api.include_router(lab_samples_router.router, dependencies=_protected)
api.include_router(noise_router.router, dependencies=_protected)
api.include_router(portal_router.router, dependencies=_protected)
# Client portal: intentionally open — access is granted by a signed,
# expiring, revocable share token carried in the URL.
api.include_router(portal_router.public)

app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    # A browser hides every response header from JavaScript except a short
    # safe list, and Content-Disposition is not on it. Without this line the
    # frontend read an empty header, failed to find a filename in it, and
    # fell back to a hardcoded name — which is why every report arrived as
    # AAQ_Report.docx however carefully the server had named it.
    #
    # `allow_headers` does not cover this: that governs what the browser may
    # send, not what it may read back.
    expose_headers=["Content-Disposition"],
)


@app.on_event("startup")
async def _on_startup() -> None:
    await create_indexes()
    await seed_pollutant_limits()
    log.info("EcoReport AI backend ready.")
