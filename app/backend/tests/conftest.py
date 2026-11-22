"""Shared pytest fixtures providing isolated SQLite DB, storage dir, and TestClient."""

import base64
from pathlib import Path
from typing import Generator

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.core.fsm import fsm
from app.db.base import Base
import app.db.session as db_session
from app.main import app as fastapi_app
from app.services.notifier import notifier
from app.ws.connection_manager import manager

VALID_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////"
    "////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
)
VALID_JPEG_BYTES = base64.b64decode(VALID_JPEG_B64)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    """Provide an isolated FastAPI TestClient backed by a fresh temp SQLite DB and storage dir."""
    storage_dir = tmp_path / "storage"
    (storage_dir / "routes").mkdir(parents=True, exist_ok=True)
    (storage_dir / "evidences").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "STORAGE_DIR", str(storage_dir))

    db_file = tmp_path / "test_patrol.db"
    test_engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False, "timeout": 15},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    monkeypatch.setattr(db_session, "engine", test_engine)
    monkeypatch.setattr(db_session, "SessionLocal", TestingSessionLocal)

    import app.models  # noqa: F401
    Base.metadata.create_all(bind=test_engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[db_session.get_db] = override_get_db
    fsm.reset()
    manager.reset()
    notifier.reset()

    with TestClient(fastapi_app) as test_client:
        yield test_client

    fastapi_app.dependency_overrides.clear()
    fsm.reset()
    manager.reset()
    notifier.reset()
    test_engine.dispose()
