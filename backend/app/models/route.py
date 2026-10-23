import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.db.base import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Route(Base):
    __tablename__ = "routes"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="SAVED")  # RECORDING, SAVED, ARCHIVED
    total_distance = Column(Float, default=0.0)    # Estimated in meters
    duration = Column(Float, default=0.0)          # Recording duration in seconds
    checkpoint_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    checkpoints = relationship(
        "Checkpoint",
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="Checkpoint.sequence_idx"
    )
    patrol_sessions = relationship("PatrolSession", back_populates="route")

class Checkpoint(Base):
    __tablename__ = "checkpoints"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    route_id = Column(String(36), ForeignKey("routes.id", ondelete="CASCADE"), nullable=False)
    sequence_idx = Column(Integer, nullable=False)
    timestamp_offset = Column(Float, default=0.0) # Seconds from start of route
    
    # Odometry / Position estimates
    x = Column(Float, default=0.0)
    y = Column(Float, default=0.0)
    theta = Column(Float, default=0.0) # Heading in radians
    
    # Recorded motor command
    linear_speed = Column(Float, default=0.0)
    angular_speed = Column(Float, default=0.0)
    
    # Visual Reference Keyframe
    keyframe_filename = Column(String(255), nullable=True)
    visual_features = Column(Text, nullable=True) # JSON descriptors or visual hash
    metadata_json = Column(Text, nullable=True)   # Additional sensor/debug payload

    # Relationships
    route = relationship("Route", back_populates="checkpoints")
