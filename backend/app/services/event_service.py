import uuid
import base64
import logging
from datetime import datetime, timezone

def utc_now() -> datetime:
    return datetime.now(timezone.utc)
from typing import List, Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.models.event import SecurityEvent, RobotLog
from app.models.patrol import PatrolSession
from app.schemas.event import SecurityEventCreate, SecurityEventResponse, RobotLogCreate
from app.services.connection_manager import manager
from app.services.robot_service import robot_service

logger = logging.getLogger("patrol_jetbot.events")

class EventService:
    def list_events(
        self,
        db: Session,
        session_id: Optional[str] = None,
        route_id: Optional[str] = None,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        resolved: Optional[bool] = None,
        skip: int = 0,
        limit: int = 50
    ) -> List[SecurityEvent]:
        query = db.query(SecurityEvent)
        if session_id:
            query = query.filter(SecurityEvent.session_id == session_id)
        if route_id:
            query = query.filter(SecurityEvent.route_id == route_id)
        if event_type:
            query = query.filter(SecurityEvent.event_type == event_type)
        if severity:
            query = query.filter(SecurityEvent.severity == severity)
        if resolved is not None:
            query = query.filter(SecurityEvent.resolved == resolved)

        return query.order_by(SecurityEvent.timestamp.desc()).offset(skip).limit(limit).all()

    def get_event(self, db: Session, event_id: str) -> Optional[SecurityEvent]:
        return db.query(SecurityEvent).filter(SecurityEvent.id == event_id).first()

    async def record_event(
        self,
        db: Session,
        data: SecurityEventCreate,
        image_bytes: Optional[bytes] = None
    ) -> SecurityEvent:
        # Determine snapshot filename
        snapshot_filename = None
        if data.image_base64:
            try:
                img_data = base64.b64decode(data.image_base64)
                snapshot_filename = f"event_{data.event_type.lower()}_{uuid.uuid4().hex[:8]}.jpg"
                file_path = settings.UPLOAD_DIR / snapshot_filename
                with open(file_path, "wb") as f:
                    f.write(img_data)
            except Exception as e:
                logger.error(f"Error decoding base64 event image: {e}")
        elif image_bytes:
            snapshot_filename = f"event_{data.event_type.lower()}_{uuid.uuid4().hex[:8]}.jpg"
            file_path = settings.UPLOAD_DIR / snapshot_filename
            with open(file_path, "wb") as f:
                f.write(image_bytes)

        # Check active session if not supplied
        session_id = data.session_id or robot_service.active_session_id
        route_id = data.route_id or robot_service.active_route_id

        # Determine severity
        severity = data.severity
        if data.event_type in ["PERSON_DETECTED", "EMERGENCY_STOP"]:
            severity = "CRITICAL"
        elif data.event_type == "OBSTACLE_BLOCKED":
            severity = "WARNING"

        event = SecurityEvent(
            session_id=session_id,
            route_id=route_id,
            event_type=data.event_type,
            severity=severity,
            confidence=data.confidence,
            bounding_box=data.bounding_box,
            snapshot_filename=snapshot_filename,
            description=data.description,
            timestamp=utc_now()
        )
        db.add(event)

        # Handle side-effects on robot mode and active session
        session = db.query(PatrolSession).filter(PatrolSession.id == session_id).first() if session_id else None

        if data.event_type == "PERSON_DETECTED":
            if session:
                session.person_detections += 1
            logger.warning(f"SECURITY ALERT: Person detected! Confidence: {data.confidence}")

        elif data.event_type == "OBSTACLE_BLOCKED":
            robot_service.current_mode = "BLOCKED"
            if session:
                session.obstacle_encounters += 1
                session.status = "BLOCKED"
            logger.warning("OBSTACLE ALERT: Robot blocked by obstacle!")

        elif data.event_type == "OBSTACLE_CLEARED":
            if session and session.status == "BLOCKED":
                session.status = "RUNNING"
                robot_service.current_mode = "REPEAT"
            else:
                robot_service.current_mode = "IDLE"
            logger.info("OBSTACLE CLEARED: Path is free, resuming robot")

        elif data.event_type == "EMERGENCY_STOP":
            robot_service.current_mode = "EMERGENCY_STOP"
            if session:
                session.status = "EMERGENCY_STOPPED"
                session.ended_at = utc_now()

        db.commit()
        db.refresh(event)

        # Broadcast event immediately to web monitoring dashboards
        event_payload = {
            "id": event.id,
            "session_id": event.session_id,
            "route_id": event.route_id,
            "event_type": event.event_type,
            "severity": event.severity,
            "confidence": event.confidence,
            "bounding_box": event.bounding_box,
            "snapshot_url": f"/api/v1/events/{event.id}/snapshot" if event.snapshot_filename else None,
            "description": event.description,
            "timestamp": event.timestamp.isoformat()
        }
        await manager.broadcast_to_web("SECURITY_EVENT", event_payload)

        return event

    def resolve_event(self, db: Session, event_id: str) -> Optional[SecurityEvent]:
        event = self.get_event(db, event_id)
        if not event:
            return None
        event.resolved = True
        db.commit()
        db.refresh(event)
        return event

    def add_log(self, db: Session, log_data: RobotLogCreate) -> RobotLog:
        log_entry = RobotLog(
            level=log_data.level,
            source=log_data.source,
            message=log_data.message
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry

    def list_logs(self, db: Session, level: Optional[str] = None, limit: int = 100) -> List[RobotLog]:
        query = db.query(RobotLog)
        if level:
            query = query.filter(RobotLog.level == level)
        return query.order_by(RobotLog.timestamp.desc()).limit(limit).all()

event_service = EventService()
