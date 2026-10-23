from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.teleop import TeleopCommand, TeleopResponse
from app.schemas.robot import EmergencyStopRequest
from app.services.robot_service import robot_service

router = APIRouter(prefix="/teleop", tags=["Teleoperation"])

@router.post("/command", response_model=TeleopResponse, summary="Send manual control command")
async def send_command(command: TeleopCommand, db: Session = Depends(get_db)):
    """
    Dispatch manual teleoperation command (FORWARD, BACKWARD, LEFT, RIGHT, STOP, EMERGENCY_STOP).
    """
    return await robot_service.handle_teleop_command(db, command)

@router.post("/emergency-stop", response_model=TeleopResponse, summary="Trigger immediate emergency stop")
async def emergency_stop(request: EmergencyStopRequest = EmergencyStopRequest(), db: Session = Depends(get_db)):
    """
    Immediately stops the JetBot motors and halts any active patrol or recording.
    """
    return await robot_service.trigger_emergency_stop(db, request.reason)
