import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.db.base import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class SecurityEvent(Base):
    __tablename__ = "security_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("patrol_sessions.id", ondelete="SET NULL"), nullable=True)
    route_id = Column(String(36), ForeignKey("routes.id", ondelete="SET NULL"), nullable=True)
    
    # Event Category & Type
    # PERSON_DETECTED, OBSTACLE_BLOCKED, OBSTACLE_CLEARED, EMERGENCY_STOP, SYSTEM_WARNING, SYSTEM_ERROR
    event_type = Column(String(30), nullable=False)
    severity = Column(String(15), default="INFO")  # INFO, WARNING, CRITICAL
    
    timestamp = Column(DateTime, default=utc_now)
    confidence = Column(Float, nullable=True)     # Detection confidence (e.g. 0.89)
    bounding_box = Column(Text, nullable=True)    # JSON string: [ymin, xmin, ymax, xmax]
    
    snapshot_filename = Column(String(255), nullable=True) # Filename in upload storage
    description = Column(Text, nullable=True)
    resolved = Column(Boolean, default=False)

    # Relationships
    patrol_session = relationship("PatrolSession", back_populates="events")

class RobotLog(Base):
    __tablename__ = "robot_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=utc_now)
    level = Column(String(10), default="INFO")     # DEBUG, INFO, WARNING, ERROR, CRITICAL
    source = Column(String(30), default="ROBOT")   # ROBOT, VISION, TELEOP, BACKEND
    message = Column(Text, nullable=False)
