from typing import Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class SecurityEventCreate(BaseModel):
    session_id: Optional[str] = None
    route_id: Optional[str] = None
    event_type: Literal[
        "PERSON_DETECTED",
        "OBSTACLE_BLOCKED",
        "OBSTACLE_CLEARED",
        "EMERGENCY_STOP",
        "SYSTEM_WARNING",
        "SYSTEM_ERROR"
    ]
    severity: Literal["INFO", "WARNING", "CRITICAL"] = "INFO"
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    bounding_box: Optional[str] = Field(None, description="JSON string or formatted coords")
    description: Optional[str] = None
    image_base64: Optional[str] = Field(None, description="Base64 encoded snapshot frame")

class SecurityEventResponse(BaseModel):
    id: str
    session_id: Optional[str] = None
    route_id: Optional[str] = None
    event_type: str
    severity: str
    timestamp: datetime
    confidence: Optional[float] = None
    bounding_box: Optional[str] = None
    snapshot_url: Optional[str] = None
    description: Optional[str] = None
    resolved: bool

    model_config = ConfigDict(from_attributes=True)

class RobotLogCreate(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    source: Literal["ROBOT", "VISION", "TELEOP", "BACKEND"] = "ROBOT"
    message: str

class RobotLogResponse(BaseModel):
    id: int
    timestamp: datetime
    level: str
    source: str
    message: str

    model_config = ConfigDict(from_attributes=True)
