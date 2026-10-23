from typing import Optional, Literal
from pydantic import BaseModel, Field

class TeleopCommand(BaseModel):
    command: Literal["FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP", "EMERGENCY_STOP"] = Field(
        ..., description="Movement command or stop action"
    )
    linear_speed: Optional[float] = Field(None, ge=0.0, le=1.0, description="Linear motor speed (0.0 to 1.0)")
    angular_speed: Optional[float] = Field(None, ge=-1.0, le=1.0, description="Steering/angular speed (-1.0 to 1.0)")
    duration: Optional[float] = Field(None, ge=0.0, le=60.0, description="Optional pulse duration in seconds")

class TeleopResponse(BaseModel):
    success: bool
    message: str
    robot_mode: str
    applied_linear: float
    applied_angular: float
