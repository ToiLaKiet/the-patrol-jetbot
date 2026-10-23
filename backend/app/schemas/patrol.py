from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class PatrolStartRequest(BaseModel):
    route_id: str = Field(..., description="UUID of the route to patrol")
    notes: Optional[str] = Field(None, description="Optional notes for this patrol session")

class PatrolProgressUpdate(BaseModel):
    current_checkpoint_idx: int = Field(..., ge=0)
    progress_percent: float = Field(..., ge=0.0, le=100.0)
    status: Optional[str] = Field(None, description="Current robot status on patrol")

class PatrolSessionResponse(BaseModel):
    id: str
    route_id: str
    route_name: Optional[str] = None
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    current_checkpoint_idx: int
    total_checkpoints: int
    progress_percent: float
    obstacle_encounters: int
    person_detections: int
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
