import logging
from datetime import datetime, timezone

def utc_now() -> datetime:
    return datetime.now(timezone.utc)
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.route import Route, Checkpoint
from app.models.patrol import PatrolSession
from app.schemas.patrol import PatrolStartRequest, PatrolProgressUpdate, PatrolSessionResponse
from app.services.connection_manager import manager
from app.services.robot_service import robot_service

logger = logging.getLogger("patrol_jetbot.patrol")

class PatrolService:
    def get_session(self, db: Session, session_id: str) -> Optional[PatrolSession]:
        return db.query(PatrolSession).filter(PatrolSession.id == session_id).first()

    def get_active_session(self, db: Session) -> Optional[PatrolSession]:
        return db.query(PatrolSession).filter(
            PatrolSession.status.in_(["STARTED", "RUNNING", "PAUSED", "BLOCKED"])
        ).order_by(PatrolSession.started_at.desc()).first()

    def list_sessions(self, db: Session, route_id: Optional[str] = None, skip: int = 0, limit: int = 20) -> List[PatrolSession]:
        query = db.query(PatrolSession)
        if route_id:
            query = query.filter(PatrolSession.route_id == route_id)
        return query.order_by(PatrolSession.started_at.desc()).offset(skip).limit(limit).all()

    async def start_patrol(self, db: Session, data: PatrolStartRequest) -> PatrolSession:
        route = db.query(Route).filter(Route.id == data.route_id).first()
        if not route:
            raise ValueError(f"Route {data.route_id} does not exist")
        if route.checkpoint_count == 0:
            raise ValueError(f"Route {data.route_id} has no checkpoints to repeat")

        # End any dangling active session
        existing_active = self.get_active_session(db)
        if existing_active:
            existing_active.status = "ABORTED"
            existing_active.ended_at = utc_now()
            db.commit()

        session = PatrolSession(
            route_id=route.id,
            status="RUNNING",
            total_checkpoints=route.checkpoint_count,
            current_checkpoint_idx=0,
            progress_percent=0.0,
            notes=data.notes
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        # Set robot mode to REPEAT
        robot_service.current_mode = "REPEAT"
        robot_service.active_route_id = route.id
        robot_service.active_session_id = session.id

        # Package route checkpoints for robot execution
        checkpoints_data = [
            {
                "sequence_idx": cp.sequence_idx,
                "x": cp.x,
                "y": cp.y,
                "theta": cp.theta,
                "linear_speed": cp.linear_speed,
                "angular_speed": cp.angular_speed,
                "keyframe_filename": cp.keyframe_filename
            }
            for cp in route.checkpoints
        ]

        payload = {
            "action": "START_PATROL",
            "session_id": session.id,
            "route_id": route.id,
            "route_name": route.name,
            "total_checkpoints": route.checkpoint_count,
            "checkpoints": checkpoints_data
        }
        await manager.send_to_robot(payload)
        await manager.broadcast_to_web("PATROL_STARTED", {
            "session_id": session.id,
            "route_id": route.id,
            "route_name": route.name,
            "total_checkpoints": route.checkpoint_count,
            "status": "RUNNING"
        })

        logger.info(f"Patrol started: Session {session.id} on route {route.name}")
        return session

    async def update_progress(self, db: Session, session_id: str, update: PatrolProgressUpdate) -> Optional[PatrolSession]:
        session = self.get_session(db, session_id)
        if not session:
            return None

        session.current_checkpoint_idx = update.current_checkpoint_idx
        session.progress_percent = update.progress_percent
        if update.status:
            session.status = update.status

        # If completed
        if update.progress_percent >= 100.0 or (session.total_checkpoints > 0 and update.current_checkpoint_idx >= session.total_checkpoints - 1):
            session.status = "COMPLETED"
            session.ended_at = utc_now()
            if robot_service.current_mode == "REPEAT":
                robot_service.current_mode = "IDLE"
                robot_service.active_session_id = None

        db.commit()
        db.refresh(session)

        # Broadcast progress
        await manager.broadcast_to_web("PATROL_PROGRESS", {
            "session_id": session.id,
            "current_checkpoint_idx": session.current_checkpoint_idx,
            "total_checkpoints": session.total_checkpoints,
            "progress_percent": session.progress_percent,
            "status": session.status
        })

        return session

    async def pause_patrol(self, db: Session, session_id: str) -> Optional[PatrolSession]:
        session = self.get_session(db, session_id)
        if not session:
            return None
        session.status = "PAUSED"
        db.commit()
        db.refresh(session)

        await manager.send_to_robot({"action": "PAUSE_PATROL", "session_id": session.id})
        await manager.broadcast_to_web("PATROL_STATUS_CHANGED", {"session_id": session.id, "status": "PAUSED"})
        return session

    async def resume_patrol(self, db: Session, session_id: str) -> Optional[PatrolSession]:
        session = self.get_session(db, session_id)
        if not session:
            return None
        session.status = "RUNNING"
        robot_service.current_mode = "REPEAT"
        db.commit()
        db.refresh(session)

        await manager.send_to_robot({"action": "RESUME_PATROL", "session_id": session.id})
        await manager.broadcast_to_web("PATROL_STATUS_CHANGED", {"session_id": session.id, "status": "RUNNING"})
        return session

    async def stop_patrol(self, db: Session, session_id: str, reason: str = "Operator aborted patrol") -> Optional[PatrolSession]:
        session = self.get_session(db, session_id)
        if not session:
            return None
        session.status = "ABORTED"
        session.ended_at = utc_now()
        session.notes = f"{session.notes or ''}\nStopped: {reason}".strip()
        db.commit()
        db.refresh(session)

        robot_service.current_mode = "IDLE"
        robot_service.active_session_id = None

        await manager.send_to_robot({"action": "STOP_PATROL", "session_id": session.id, "reason": reason})
        await manager.broadcast_to_web("PATROL_STATUS_CHANGED", {"session_id": session.id, "status": "ABORTED", "reason": reason})
        return session

patrol_service = PatrolService()
