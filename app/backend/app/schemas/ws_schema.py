"""WebSocket message schemas shared between JetBot, Backend, and Frontend."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


# [PENDING_INTEGRATION: FRONTEND_WS_TOPICS]
# Hiện tại: Chuẩn hóa thông điệp WebSocket theo dạng JSON có trường `type` (robot->server->web) và `cmd` (web->server->robot).
# Cần khớp: Tên các trường trong payload WebSocket (telemetry, event, frame, status, move, emergency_stop) với Frontend.
# Hành động: Cập nhật schema và bộ chuẩn hóa lệnh dưới đây nếu Frontend dùng tên topic hoặc tên trường khác.

_CMD_ALIASES = {
    "teleop": "move",
    "pause": "pause_patrol",
    "resume": "resume_patrol",
}


def normalize_web_command(raw_cmd: str) -> str:
    """Normalize command aliases sent from Web UI into canonical backend commands."""
    cleaned = raw_cmd.strip().lower()
    return _CMD_ALIASES.get(cleaned, cleaned)


class RobotTelemetryMessage(BaseModel):
    """Telemetry payload sent periodically by JetBot over /ws/robot."""

    type: str = "telemetry"
    run_id: Optional[str] = None
    state: str = "IDLE"
    checkpoint_seq: Optional[int] = None
    total_checkpoints: Optional[int] = None
    match_score: Optional[float] = None
    battery_v: float = 11.5
    battery_pct: int = Field(default=80, ge=0, le=100)
    timestamp: Optional[str] = None


class RobotEventMessage(BaseModel):
    """Event payload emitted by JetBot CV pipeline over /ws/robot."""

    type: str = "event"
    run_id: Optional[str] = None
    event_type: str
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    image_base64: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[str] = None


class RobotStatusMessage(BaseModel):
    """State or patrol lifecycle transition message emitted by JetBot."""

    type: str = "status"
    run_id: Optional[str] = None
    state: Optional[str] = None
    patrol_status: Optional[str] = None
    result: Optional[str] = None
    note: Optional[str] = None
    timestamp: Optional[str] = None


class WebCommandMessage(BaseModel):
    """Control command received from Web UI over /ws/web."""

    cmd: str = Field(..., min_length=1)
    left: Optional[float] = Field(default=0.0, ge=-1.0, le=1.0)
    right: Optional[float] = Field(default=0.0, ge=-1.0, le=1.0)
    hold: bool = False
    route_id: Optional[str] = None
    run_id: Optional[str] = None
