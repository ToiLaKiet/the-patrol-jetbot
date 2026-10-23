from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean
from app.db.base import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class RobotState(Base):
    __tablename__ = "robot_states"

    id = Column(Integer, primary_key=True, default=1)
    robot_id = Column(String(50), default="jetbot_01", unique=True)
    connection_status = Column(String(20), default="DISCONNECTED") # CONNECTED, DISCONNECTED
    current_mode = Column(String(20), default="IDLE")              # IDLE, MANUAL, TEACH, REPEAT, BLOCKED, EMERGENCY_STOP
    
    battery_percentage = Column(Float, default=100.0)
    battery_voltage = Column(Float, default=12.4)
    wifi_rssi = Column(Integer, default=-50) # dBm
    
    linear_speed = Column(Float, default=0.0)
    angular_speed = Column(Float, default=0.0)
    
    current_x = Column(Float, default=0.0)
    current_y = Column(Float, default=0.0)
    current_heading = Column(Float, default=0.0)
    
    active_route_id = Column(String(36), nullable=True)
    active_session_id = Column(String(36), nullable=True)
    
    last_heartbeat = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
