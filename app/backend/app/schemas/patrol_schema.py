"""Pydantic schemas for patrol runs, telemetry points, and KPI summaries."""

from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class PatrolStartRequest(BaseModel):
    """Request body to start a new autonomous patrol run."""

    route_id: str = Field(..., min_length=1, max_length=36)
    note: Optional[str] = Field(default=None, max_length=500)


class PatrolFinishRequest(BaseModel):
    """Request body to finalize an active patrol run."""

    result: Literal["COMPLETED", "ABORTED", "LOST"]
    note: Optional[str] = Field(default=None, max_length=500)


class PatrolRunResponse(BaseModel):
    """Serialized patrol run record."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    route_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    result: str
    obstacle_count: int
    person_count: int
    note: Optional[str] = None


class TelemetryPointResponse(BaseModel):
    """Serialized telemetry sample belonging to a patrol run."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    timestamp: datetime
    state: Optional[str] = None
    checkpoint_seq: Optional[int] = None
    match_score: Optional[float] = None
    battery_v: Optional[float] = None
    battery_pct: Optional[int] = None
    latency_ms: Optional[float] = None


class RouteKPIItem(BaseModel):
    """Per-route patrol completion statistics."""

    route_id: str
    route_name: str
    total_runs: int
    completed_runs: int
    aborted_runs: int
    lost_runs: int
    in_progress_runs: int
    completion_rate_pct: float


class PatrolKPISummaryResponse(BaseModel):
    """Aggregated acceptance-criteria KPI report across all patrol runs and events."""

    total_runs: int
    completed_runs: int
    aborted_runs: int
    lost_runs: int
    in_progress_runs: int
    completion_rate_pct: float
    total_obstacles_blocked: int
    total_obstacles_cleared: int
    obstacle_stop_resume_rate_pct: float
    total_persons_detected: int
    per_route: List[RouteKPIItem] = Field(default_factory=list)
