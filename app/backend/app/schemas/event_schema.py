"""Pydantic schemas for security and operational events."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field


class EventCreate(BaseModel):
    """Request body for recording a security or obstacle event via REST."""

    run_id: Optional[str] = Field(default=None, max_length=36)
    type: str = Field(..., min_length=1, max_length=50)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    image_base64: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    payload_json: Optional[Dict[str, Any]] = None
    bypass_cooldown: bool = False


class EventResponse(BaseModel):
    """Serialized security event with optional URL to evidence image."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: Optional[str] = None
    type: str
    timestamp: datetime
    confidence: Optional[float] = None
    evidence_path: Optional[str] = None
    payload_json: Optional[Dict[str, Any]] = None

    @computed_field
    @property
    def evidence_url(self) -> Optional[str]:
        if not self.evidence_path:
            return None
        clean = self.evidence_path.lstrip("/")
        return f"/storage/{clean}"


class EventListResponse(BaseModel):
    """Paginated response for security event queries."""

    total: int
    skip: int
    limit: int
    items: List[EventResponse]
