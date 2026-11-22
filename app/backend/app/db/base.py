"""SQLAlchemy declarative base and shared timestamp helper."""

from datetime import datetime, timezone
from sqlalchemy.orm import DeclarativeBase


def utc_now() -> datetime:
    """Return naive UTC datetime compatible with SQLite DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
