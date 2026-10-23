import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.db.base import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class PatrolSession(Base):
    __tablename__ = "patrol_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    route_id = Column(String(36), ForeignKey("routes.id"), nullable=False)
    status = Column(String(25), default="STARTED")  # STARTED, RUNNING, PAUSED, BLOCKED, COMPLETED, ABORTED, EMERGENCY_STOPPED
    
    started_at = Column(DateTime, default=utc_now)
    ended_at = Column(DateTime, nullable=True)
    
    current_checkpoint_idx = Column(Integer, default=0)
    total_checkpoints = Column(Integer, default=0)
    progress_percent = Column(Float, default=0.0)
    
    obstacle_encounters = Column(Integer, default=0)
    person_detections = Column(Integer, default=0)
    notes = Column(Text, nullable=True)

    # Relationships
    route = relationship("Route", back_populates="patrol_sessions")
    events = relationship(
        "SecurityEvent",
        back_populates="patrol_session",
        cascade="all, delete-orphan",
        order_by="SecurityEvent.timestamp.desc()"
    )
