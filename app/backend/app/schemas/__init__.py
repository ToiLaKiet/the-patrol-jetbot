"""Pydantic v2 schemas for REST API and WebSocket payloads."""

from app.schemas.event_schema import EventCreate, EventListResponse, EventResponse
from app.schemas.patrol_schema import (
    PatrolFinishRequest,
    PatrolKPISummaryResponse,
    PatrolRunResponse,
    PatrolStartRequest,
    RouteKPIItem,
    TelemetryPointResponse,
)
from app.schemas.route_schema import (
    CheckpointCreate,
    CheckpointResponse,
    RouteCreate,
    RouteDetailResponse,
    RouteResponse,
    RouteUploadResponse,
)
from app.schemas.ws_schema import (
    RobotEventMessage,
    RobotStatusMessage,
    RobotTelemetryMessage,
    WebCommandMessage,
    normalize_web_command,
)

__all__ = [
    "CheckpointCreate",
    "CheckpointResponse",
    "RouteCreate",
    "RouteResponse",
    "RouteDetailResponse",
    "RouteUploadResponse",
    "PatrolStartRequest",
    "PatrolFinishRequest",
    "PatrolRunResponse",
    "TelemetryPointResponse",
    "RouteKPIItem",
    "PatrolKPISummaryResponse",
    "EventCreate",
    "EventResponse",
    "EventListResponse",
    "RobotTelemetryMessage",
    "RobotEventMessage",
    "RobotStatusMessage",
    "WebCommandMessage",
    "normalize_web_command",
]
