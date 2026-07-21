"""EcoReport AI — FastAPI backend entrypoint (Phase 1 skeleton)."""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from db import create_indexes, seed_pollutant_limits
from auth import current_user
from routes import auth_routes as auth_router
from routes import campaigns as campaigns_router
from routes import limits as limits_router
from routes import readings as readings_router
from routes import history as history_router
from routes import report as report_router
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
_protected = [_Depends(current_user)]
api.include_router(campaigns_router.router, dependencies=_protected)
api.include_router(readings_router.router, dependencies=_protected)
api.include_router(limits_router.router, dependencies=_protected)
api.include_router(summary_router.router, dependencies=_protected)
api.include_router(report_router.router, dependencies=_protected)
api.include_router(history_router.router, dependencies=_protected)

app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _on_startup() -> None:
    await create_indexes()
    await seed_pollutant_limits()
    log.info("EcoReport AI backend ready.")
