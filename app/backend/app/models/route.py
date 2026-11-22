"""ORM models for taught routes and ordered checkpoints."""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base, utc_now


class Route(Base):
    """Patrol route recorded during Teach Mode or uploaded as a route package."""

    __tablename__ = "routes"

    id = Column(String(36), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    checkpoint_count = Column(Integer, default=0, nullable=False)
    total_duration_s = Column(Float, default=0.0, nullable=False)
    status = Column(String(20), default="ACTIVE", nullable=False)
    package_path = Column(String(255), nullable=True)

    checkpoints = relationship(
        "Checkpoint",
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="Checkpoint.seq",
    )
    patrol_runs = relationship(
        "PatrolRun",
        back_populates="route",
        cascade="all, delete-orphan",
    )


class Checkpoint(Base):
    """Ordered checkpoint node along a Teach & Repeat route (no absolute x/y map)."""

    __tablename__ = "checkpoints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    route_id = Column(
        String(36),
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq = Column(Integer, nullable=False)
    keyframe_path = Column(String(255), nullable=True)
    timestamp_offset = Column(Float, default=0.0, nullable=False)
    command_summary = Column(String(255), nullable=True)

    route = relationship("Route", back_populates="checkpoints")
