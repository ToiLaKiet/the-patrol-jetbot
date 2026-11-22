"""Version 1 REST API router registry."""

from fastapi import APIRouter

from app.api.v1.events import events_router
from app.api.v1.patrols import patrols_router
from app.api.v1.routes import routes_router
from app.api.v1.telemetry import telemetry_router

api_v1_router = APIRouter()
api_v1_router.include_router(routes_router)
api_v1_router.include_router(patrols_router)
api_v1_router.include_router(events_router)
api_v1_router.include_router(telemetry_router)

__all__ = ["api_v1_router"]
