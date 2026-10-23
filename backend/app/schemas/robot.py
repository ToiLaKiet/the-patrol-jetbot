from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class RobotTelemetry(BaseModel):
    robot_id: str = "jetbot_01"
    connection_status: Optional[str] = "CONNECTED"
    current_mode: Optional[str] = "IDLE"  # IDLE, MANUAL, TEACH, REPEAT, BLOCKED, EMERGENCY_STOP
    battery_percentage: Optional[float] = Field(100.0, ge=0.0, le=100.0)
    battery_voltage: Optional[float] = Field(12.0, ge=0.0, le=24.0)
    wifi_rssi: Optional[int] = Field(-50, ge=-120, le=0)
    linear_speed: Optional[float] = 0.0
    angular_speed: Optional[float] = 0.0
    current_x: Optional[float] = 0.0
    current_y: Optional[float] = 0.0
    current_heading: Optional[float] = 0.0
    active_route_id: Optional[str] = None
    active_session_id: Optional[str] = None

class RobotStatusResponse(RobotTelemetry):
    is_online: bool = True
    last_heartbeat: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class EmergencyStopRequest(BaseModel):
    reason: Optional[str] = "Manual emergency stop triggered from Web App"
