"""FastAPI application factory, lifecycle tasks, CORS, and router mounting."""

import asyncio
from contextlib import asynccontextmanager, suppress
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import api_v1_router
from app.config import settings
from app.core.fsm import fsm
from app.db.base import utc_now
import app.db.session as db_session
from app.models.patrol import PatrolRun
from app.ws.connection_manager import manager
from app.ws.router import ws_router

logger = logging.getLogger("patrol_backend")


def _ensure_storage_dirs() -> None:
    root = Path(settings.STORAGE_DIR)
    (root / "routes").mkdir(parents=True, exist_ok=True)
    (root / "evidences").mkdir(parents=True, exist_ok=True)


async def _heartbeat_monitor_loop() -> None:
    """Periodically check whether the connected JetBot missed its heartbeat deadline."""
    while True:
        await asyncio.sleep(1.0)
        if fsm.is_heartbeat_expired():
            logger.warning("JetBot heartbeat expired; marking OFFLINE.")
            active_run_id = fsm.active_run_id
            fsm.on_robot_disconnected()
            manager.disconnect_robot()

            if active_run_id:
                session = db_session.SessionLocal()
                try:
                    run_obj = session.get(PatrolRun, active_run_id)
                    if run_obj is not None and run_obj.result == "IN_PROGRESS":
                        run_obj.result = "ABORTED"
                        run_obj.ended_at = utc_now()
                        run_obj.note = "Heartbeat timeout"
                        session.commit()
                finally:
                    session.close()
                fsm.active_run_id = None

            await manager.broadcast_to_web(
                {
                    "type": "system",
                    "state": "OFFLINE",
                    "robot_connected": False,
                    "message": "Mất heartbeat từ JetBot (OFFLINE)!",
                    "timestamp": utc_now().isoformat(),
                }
            )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize SQLite schema, ensure storage folders, and run background heartbeat monitor."""
    _ensure_storage_dirs()
    db_session.init_db()
    monitor_task = asyncio.create_task(_heartbeat_monitor_loop())
    try:
        yield
    finally:
        monitor_task.cancel()
        with suppress(asyncio.CancelledError):
            await monitor_task


_ensure_storage_dirs()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="2.0.0",
    description="FastAPI & WebSocket Middleware cho hệ thống robot tuần tra The Patrol JetBot",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix=settings.API_V1_STR)
app.include_router(ws_router)
app.mount("/storage", StaticFiles(directory=settings.STORAGE_DIR), name="storage")


@app.get("/", tags=["Health"])
def read_root():
    """Return service overview and key documentation/WebSocket endpoints."""
    return {
        "service": settings.PROJECT_NAME,
        "version": "2.0.0",
        "docs_url": "/docs",
        "health_url": "/health",
        "api_prefix": settings.API_V1_STR,
        "ws_robot": "/ws/robot",
        "ws_web": "/ws/web",
    }


@app.get("/health", tags=["Health"])
def health_check():
    """Lightweight liveness check reporting current robot connection state."""
    return {
        "status": "ok",
        "robot_connected": fsm.robot_connected,
        "robot_state": fsm.state.value,
    }
