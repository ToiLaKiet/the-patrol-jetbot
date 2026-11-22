"""Pydantic schemas for routes and checkpoints."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CheckpointCreate(BaseModel):
    """Input schema for registering a route checkpoint (no absolute coordinates)."""

    seq: int = Field(..., ge=0)
    keyframe_path: Optional[str] = Field(default=None, max_length=255)
    timestamp_offset: float = Field(default=0.0, ge=0.0)
    command_summary: Optional[str] = Field(default=None, max_length=255)


class CheckpointResponse(BaseModel):
    """Serialized checkpoint item."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    route_id: str
    seq: int
    keyframe_path: Optional[str] = None
    timestamp_offset: float
    command_summary: Optional[str] = None


class RouteCreate(BaseModel):
    """Input schema for creating a route record via JSON."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=255)
    total_duration_s: float = Field(default=0.0, ge=0.0)
    checkpoints: List[CheckpointCreate] = Field(default_factory=list)


class RouteResponse(BaseModel):
    """Summary response for a stored route."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str] = None
    created_at: datetime
    checkpoint_count: int
    total_duration_s: float
    status: str
    package_path: Optional[str] = None


class RouteDetailResponse(RouteResponse):
    """Detailed route response including ordered checkpoints."""

    checkpoints: List[CheckpointResponse] = Field(default_factory=list)


class RouteUploadResponse(BaseModel):
    """Response returned after uploading and unpacking a route ZIP package."""

    message: str
    route: RouteDetailResponse
