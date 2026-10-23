from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class CheckpointBase(BaseModel):
    sequence_idx: int
    timestamp_offset: float = 0.0
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0
    linear_speed: float = 0.0
    angular_speed: float = 0.0
    visual_features: Optional[str] = None
    metadata_json: Optional[str] = None

class CheckpointCreate(CheckpointBase):
    keyframe_base64: Optional[str] = Field(None, description="Base64 encoded JPEG/PNG keyframe image")

class CheckpointResponse(CheckpointBase):
    id: str
    route_id: str
    keyframe_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class RouteBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None

class RouteCreate(RouteBase):
    pass

class RouteStartRecording(RouteBase):
    pass

class RouteUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None

class RouteResponse(RouteBase):
    id: str
    status: str
    total_distance: float
    duration: float
    checkpoint_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    checkpoints: Optional[List[CheckpointResponse]] = None

    model_config = ConfigDict(from_attributes=True)

class RouteExport(RouteResponse):
    pass
