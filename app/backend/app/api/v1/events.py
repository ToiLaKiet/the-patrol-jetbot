"""REST API endpoints for querying, recording, and uploading security events."""

from datetime import datetime
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models.event import SecurityEvent
from app.models.patrol import PatrolRun
from app.schemas.event_schema import EventCreate, EventListResponse, EventResponse
from app.services.notifier import notifier, save_evidence_base64, save_evidence_bytes
from app.ws.connection_manager import manager

events_router = APIRouter(prefix="/events", tags=["Events"])


def _increment_run_counters(db: Session, run_id: Optional[str], event_type: str) -> None:
    if not run_id:
        return
    run_obj = db.get(PatrolRun, run_id)
    if run_obj is None:
        return
    if "PERSON" in event_type:
        run_obj.person_count += 1
    elif event_type == "OBSTACLE_BLOCKED":
        run_obj.obstacle_count += 1


@events_router.get("/", response_model=EventListResponse)
def list_events(
    event_type: Optional[str] = Query(default=None),
    run_id: Optional[str] = Query(default=None),
    start_time: Optional[datetime] = Query(default=None),
    end_time: Optional[datetime] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Query security and operational events with filters and pagination."""
    query = db.query(SecurityEvent)
    if event_type:
        query = query.filter(SecurityEvent.type == event_type.strip().upper())
    if run_id:
        query = query.filter(SecurityEvent.run_id == run_id)
    if start_time:
        query = query.filter(SecurityEvent.timestamp >= start_time)
    if end_time:
        query = query.filter(SecurityEvent.timestamp <= end_time)

    total = query.count()
    items = (
        query.order_by(SecurityEvent.timestamp.desc(), SecurityEvent.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return EventListResponse(total=total, skip=skip, limit=limit, items=items)


@events_router.get("/{event_id}", response_model=EventResponse)
def get_event_detail(event_id: int, db: Session = Depends(get_db)):
    """Retrieve a single security event by ID."""
    event_rec = db.get(SecurityEvent, event_id)
    if event_rec is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy sự kiện")
    return event_rec


# [PENDING_INTEGRATION: TUANANH_EVENT_PAYLOAD]
# Hiện tại: Hỗ trợ nhận sự kiện qua JSON (image_base64) hoặc multipart upload ảnh bằng chứng (/upload).
# Cần khớp: Cách Tuấn Anh chọn gửi ảnh phát hiện người/vật cản từ YOLO/CV.
# Hành động: Giữ endpoint phù hợp và chuẩn hóa payload_json sau khi tích hợp mô hình thực tế.
@events_router.post("/", response_model=EventResponse, status_code=201)
async def create_event(
    payload: EventCreate,
    db: Session = Depends(get_db),
):
    """Record a security event via JSON payload (supporting optional base64 evidence)."""
    event_type = payload.type.strip().upper()
    evidence_path: Optional[str] = None
    if payload.image_base64:
        try:
            evidence_path = save_evidence_base64(
                payload.image_base64,
                storage_dir=settings.STORAGE_DIR,
                prefix=event_type.lower(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    details = payload.payload_json if payload.payload_json is not None else payload.details
    event_rec = SecurityEvent(
        run_id=payload.run_id,
        type=event_type,
        confidence=payload.confidence,
        evidence_path=evidence_path,
        payload_json=details,
    )
    db.add(event_rec)
    _increment_run_counters(db, payload.run_id, event_type)
    db.commit()
    db.refresh(event_rec)

    if payload.bypass_cooldown or notifier.should_notify(event_type):
        serialized = EventResponse.model_validate(event_rec).model_dump(mode="json")
        serialized["event_type"] = event_type
        await manager.broadcast_to_web({"type": "event", "data": serialized})

    return event_rec


@events_router.post("/upload", response_model=EventResponse, status_code=201)
async def upload_event_with_image(
    type: str = Form(...),
    run_id: Optional[str] = Form(default=None),
    confidence: Optional[float] = Form(default=None),
    details_json: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Record a security event along with a multipart-uploaded evidence image."""
    event_type = type.strip().upper()
    parsed_details = None
    if details_json:
        try:
            parsed_details = json.loads(details_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="details_json không hợp lệ") from exc

    raw_bytes = await file.read()
    ext = Path(file.filename or "evidence.jpg").suffix or ".jpg"
    try:
        evidence_path = save_evidence_bytes(
            raw_bytes,
            ext=ext,
            storage_dir=settings.STORAGE_DIR,
            prefix=event_type.lower(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    event_rec = SecurityEvent(
        run_id=run_id,
        type=event_type,
        confidence=confidence,
        evidence_path=evidence_path,
        payload_json=parsed_details,
    )
    db.add(event_rec)
    _increment_run_counters(db, run_id, event_type)
    db.commit()
    db.refresh(event_rec)

    if notifier.should_notify(event_type):
        serialized = EventResponse.model_validate(event_rec).model_dump(mode="json")
        serialized["event_type"] = event_type
        await manager.broadcast_to_web({"type": "event", "data": serialized})

    return event_rec


@events_router.delete("/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)):
    """Delete a security event and its associated evidence file on disk if present."""
    event_rec = db.get(SecurityEvent, event_id)
    if event_rec is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy sự kiện")

    evidence_rel = event_rec.evidence_path
    db.delete(event_rec)
    db.commit()

    if evidence_rel:
        storage_root = Path(settings.STORAGE_DIR).resolve()
        candidate = (storage_root / evidence_rel).resolve()
        try:
            candidate.relative_to(storage_root)
            if candidate.is_file():
                candidate.unlink()
        except ValueError:
            pass

    return {"message": "Đã xóa sự kiện", "event_id": event_id}
