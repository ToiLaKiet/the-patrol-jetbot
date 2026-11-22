"""SQLite database engine, session factory, and schema initialization."""

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.base import Base

_connect_args = (
    {"check_same_thread": False, "timeout": 15}
    if settings.DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Yield a scoped SQLAlchemy session per request or WebSocket lifecycle."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Import all ORM models and create missing database tables."""
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
