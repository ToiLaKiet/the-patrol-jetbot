import math
import uuid
import base64
import logging
from datetime import datetime, timezone

def utc_now() -> datetime:
    return datetime.now(timezone.utc)
from typing import List, Optional, Tuple
from pathlib import Path
from sqlalchemy.orm import Session
from app.config import settings
from app.models.route import Route, Checkpoint
from app.schemas.route import (
    RouteCreate, RouteUpdate, RouteResponse, RouteStartRecording,
    CheckpointCreate, CheckpointResponse
)
from app.services.connection_manager import manager
from app.services.robot_service import robot_service

logger = logging.getLogger("patrol_jetbot.route")

class RouteService:
    def list_routes(self, db: Session, skip: int = 0, limit: int = 50) -> List[Route]:
        return db.query(Route).filter(Route.is_active == True).order_by(Route.created_at.desc()).offset(skip).limit(limit).all()

    def get_route(self, db: Session, route_id: str) -> Optional[Route]:
        return db.query(Route).filter(Route.id == route_id).first()

    def create_route(self, db: Session, data: RouteCreate) -> Route:
        route = Route(
            name=data.name,
            description=data.description,
            status="SAVED"
        )
        db.add(route)
        db.commit()
        db.refresh(route)
        return route

    async def start_recording(self, db: Session, data: RouteStartRecording) -> Route:
        """Start route recording in TEACH mode"""
        route = Route(
            name=data.name,
            description=data.description,
            status="RECORDING",
            checkpoint_count=0,
            duration=0.0,
            total_distance=0.0
        )
        db.add(route)
        db.commit()
        db.refresh(route)

        # Update robot mode to TEACH
        robot_service.current_mode = "TEACH"
        robot_service.active_route_id = route.id

        # Notify robot and web clients
        payload = {
            "action": "START_TEACH_MODE",
            "route_id": route.id,
            "route_name": route.name
        }
        await manager.send_to_robot(payload)
        await manager.broadcast_to_web("TEACH_STARTED", {
            "route_id": route.id,
            "route_name": route.name,
            "status": "RECORDING"
        })

        logger.info(f"Started route recording: {route.id} ({route.name})")
        return route

    async def add_checkpoint(self, db: Session, route_id: str, data: CheckpointCreate) -> Checkpoint:
        """Add recorded checkpoint with optional keyframe image"""
        route = self.get_route(db, route_id)
        if not route:
            raise ValueError(f"Route with id {route_id} not found")

        keyframe_filename = None
        if data.keyframe_base64:
            try:
                # Save base64 keyframe to disk
                img_data = base64.b64decode(data.keyframe_base64)
                keyframe_filename = f"keyframe_{route_id}_{data.sequence_idx}_{uuid.uuid4().hex[:6]}.jpg"
                file_path = settings.KEYFRAME_DIR / keyframe_filename
                with open(file_path, "wb") as f:
                    f.write(img_data)
            except Exception as e:
                logger.error(f"Error saving keyframe: {e}")

        # Calculate incremental distance if previous checkpoints exist
        last_cp = db.query(Checkpoint).filter(
            Checkpoint.route_id == route_id
        ).order_by(Checkpoint.sequence_idx.desc()).first()

        added_dist = 0.0
        if last_cp:
            added_dist = math.sqrt((data.x - last_cp.x)**2 + (data.y - last_cp.y)**2)

        checkpoint = Checkpoint(
            route_id=route_id,
            sequence_idx=data.sequence_idx,
            timestamp_offset=data.timestamp_offset,
            x=data.x,
            y=data.y,
            theta=data.theta,
            linear_speed=data.linear_speed,
            angular_speed=data.angular_speed,
            keyframe_filename=keyframe_filename,
            visual_features=data.visual_features,
            metadata_json=data.metadata_json
        )
        db.add(checkpoint)

        # Update route summary stats
        route.checkpoint_count += 1
        route.total_distance += added_dist
        route.duration = max(route.duration, data.timestamp_offset)
        route.updated_at = utc_now()

        db.commit()
        db.refresh(checkpoint)

        # Broadcast checkpoint added
        await manager.broadcast_to_web("CHECKPOINT_ADDED", {
            "route_id": route_id,
            "checkpoint_idx": data.sequence_idx,
            "x": data.x,
            "y": data.y,
            "total_checkpoints": route.checkpoint_count
        })

        return checkpoint

    async def stop_recording(self, db: Session, route_id: str) -> Route:
        """Finish and finalize route recording"""
        route = self.get_route(db, route_id)
        if not route:
            raise ValueError(f"Route with id {route_id} not found")

        route.status = "SAVED"
        route.updated_at = utc_now()
        db.commit()
        db.refresh(route)

        # Reset robot mode from TEACH to IDLE
        if robot_service.current_mode == "TEACH":
            robot_service.current_mode = "IDLE"
            robot_service.active_route_id = None

        payload = {
            "action": "STOP_TEACH_MODE",
            "route_id": route.id,
            "checkpoint_count": route.checkpoint_count,
            "total_distance": round(route.total_distance, 2)
        }
        await manager.send_to_robot(payload)
        await manager.broadcast_to_web("TEACH_FINISHED", {
            "route_id": route.id,
            "checkpoint_count": route.checkpoint_count,
            "total_distance": round(route.total_distance, 2),
            "status": "SAVED"
        })

        logger.info(f"Route recording finished: {route.id} with {route.checkpoint_count} checkpoints")
        return route

    def update_route(self, db: Session, route_id: str, data: RouteUpdate) -> Optional[Route]:
        route = self.get_route(db, route_id)
        if not route:
            return None
        if data.name is not None:
            route.name = data.name
        if data.description is not None:
            route.description = data.description
        if data.status is not None:
            route.status = data.status
        if data.is_active is not None:
            route.is_active = data.is_active
        route.updated_at = utc_now()
        db.commit()
        db.refresh(route)
        return route

    def delete_route(self, db: Session, route_id: str) -> bool:
        route = self.get_route(db, route_id)
        if not route:
            return False
        # Remove keyframe image files
        for cp in route.checkpoints:
            if cp.keyframe_filename:
                file_path = settings.KEYFRAME_DIR / cp.keyframe_filename
                if file_path.exists():
                    file_path.unlink()
        db.delete(route)
        db.commit()
        return True

route_service = RouteService()
