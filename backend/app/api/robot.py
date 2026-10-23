from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.robot import RobotTelemetry, RobotStatusResponse
from app.services.robot_service import robot_service

router = APIRouter(prefix="/robot", tags=["Robot Status & Telemetry"])

@router.get("/status", response_model=RobotStatusResponse, summary="Get current robot status and telemetry")
def get_status(db: Session = Depends(get_db)):
    """
    Returns live robot state (battery, connection, mode, speed, position, active route).
    """
    return robot_service.get_status()

@router.post("/telemetry", response_model=RobotStatusResponse, summary="Push telemetry from robot/simulator")
async def push_telemetry(telemetry: RobotTelemetry, db: Session = Depends(get_db)):
    """
    HTTP endpoint for robot or simulator to report its telemetry.
    """
    return await robot_service.update_telemetry(db, telemetry)

@router.post("/heartbeat", summary="Send robot heartbeat ping")
def heartbeat():
    robot_service.last_heartbeat = datetime.now(timezone.utc)
    return {"status": "ok", "timestamp": robot_service.last_heartbeat.isoformat()}
