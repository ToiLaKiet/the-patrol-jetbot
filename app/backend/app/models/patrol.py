"""ORM models for autonomous patrol runs and time-series run telemetry."""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base, utc_now


class PatrolRun(Base):
    """Single autonomous patrol execution record used for KPI evaluation."""

    __tablename__ = "patrol_runs"

    id = Column(String(36), primary_key=True, index=True)
    route_id = Column(
        String(36),
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at = Column(DateTime, default=utc_now, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    result = Column(String(20), default="IN_PROGRESS", nullable=False)  # IN_PROGRESS, COMPLETED, ABORTED, LOST
    obstacle_count = Column(Integer, default=0, nullable=False)
    person_count = Column(Integer, default=0, nullable=False)
    note = Column(String(500), nullable=True)

    route = relationship("Route", back_populates="patrol_runs")
    telemetry = relationship(
        "RunTelemetry",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="RunTelemetry.timestamp",
    )


class RunTelemetry(Base):
    """Per-tick telemetry sample persisted during an active patrol run."""

    __tablename__ = "run_telemetry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(
        String(36),
        ForeignKey("patrol_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timestamp = Column(DateTime, default=utc_now, nullable=False, index=True)
    state = Column(String(20), nullable=True)
    checkpoint_seq = Column(Integer, nullable=True)
    match_score = Column(Float, nullable=True)
    battery_v = Column(Float, nullable=True)
    battery_pct = Column(Integer, nullable=True)
    latency_ms = Column(Float, nullable=True)

    run = relationship("PatrolRun", back_populates="telemetry")
