from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.config import settings
from app.db.session import get_db
from app.schemas.event import (
    SecurityEventCreate, SecurityEventResponse, RobotLogCreate, RobotLogResponse
)
from app.services.event_service import event_service

router = APIRouter(prefix="/events", tags=["Security & Obstacle Events"])

def _build_event_response(ev) -> SecurityEventResponse:
    snapshot_url = f"/api/v1/events/{ev.id}/snapshot" if ev.snapshot_filename else None
    return SecurityEventResponse(
        id=ev.id,
        session_id=ev.session_id,
        route_id=ev.route_id,
        event_type=ev.event_type,
        severity=ev.severity,
        timestamp=ev.timestamp,
        confidence=ev.confidence,
        bounding_box=ev.bounding_box,
        snapshot_url=snapshot_url,
        description=ev.description,
        resolved=ev.resolved
    )

@router.get("", response_model=List[SecurityEventResponse], summary="List security and obstacle events")
def list_events(
    session_id: Optional[str] = None,
    route_id: Optional[str] = None,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    resolved: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    events = event_service.list_events(
        db,
        session_id=session_id,
        route_id=route_id,
        event_type=event_type,
        severity=severity,
        resolved=resolved,
        skip=skip,
        limit=limit
    )
    return [_build_event_response(e) for e in events]

@router.post("", response_model=SecurityEventResponse, summary="Record a new security or obstacle event")
async def record_event(data: SecurityEventCreate, db: Session = Depends(get_db)):
    event = await event_service.record_event(db, data)
    return _build_event_response(event)

@router.post("/upload-snapshot", response_model=SecurityEventResponse, summary="Record event with image file upload")
async def upload_event_with_image(
    event_type: str = Form(...),
    severity: str = Form("INFO"),
    session_id: Optional[str] = Form(None),
    route_id: Optional[str] = Form(None),
    confidence: Optional[float] = Form(None),
    bounding_box: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    image_bytes = await image.read()
    data = SecurityEventCreate(
        event_type=event_type, # type: ignore
        severity=severity,     # type: ignore
        session_id=session_id,
        route_id=route_id,
        confidence=confidence,
        bounding_box=bounding_box,
        description=description
    )
    event = await event_service.record_event(db, data, image_bytes=image_bytes)
    return _build_event_response(event)

@router.get("/{event_id}", response_model=SecurityEventResponse, summary="Get event details")
def get_event(event_id: str, db: Session = Depends(get_db)):
    event = event_service.get_event(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return _build_event_response(event)

@router.post("/{event_id}/resolve", response_model=SecurityEventResponse, summary="Acknowledge/resolve event")
def resolve_event(event_id: str, db: Session = Depends(get_db)):
    event = event_service.resolve_event(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return _build_event_response(event)

@router.get("/{event_id}/snapshot", summary="View or download snapshot image")
def get_snapshot(event_id: str, db: Session = Depends(get_db)):
    event = event_service.get_event(db, event_id)
    if not event or not event.snapshot_filename:
        raise HTTPException(status_code=404, detail="Snapshot not found for this event")
    file_path = settings.UPLOAD_DIR / event.snapshot_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Snapshot file missing on disk")
    return FileResponse(file_path, media_type="image/jpeg")

@router.get("/system/logs", response_model=List[RobotLogResponse], summary="List system logs")
def list_logs(level: Optional[str] = None, limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    logs = event_service.list_logs(db, level=level, limit=limit)
    return logs

@router.post("/system/logs", response_model=RobotLogResponse, summary="Create system log entry")
def create_log(log_data: RobotLogCreate, db: Session = Depends(get_db)):
    return event_service.add_log(db, log_data)
