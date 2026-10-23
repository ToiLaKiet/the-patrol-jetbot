import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.schemas.robot import RobotTelemetry
from app.schemas.teleop import TeleopCommand
from app.schemas.patrol import PatrolProgressUpdate
from app.schemas.event import SecurityEventCreate
from app.services.connection_manager import manager
from app.services.video_streamer import video_streamer
from app.services.robot_service import robot_service
from app.services.patrol_service import patrol_service
from app.services.event_service import event_service

logger = logging.getLogger("patrol_jetbot.ws")

router = APIRouter(prefix="/ws", tags=["WebSockets"])

@router.websocket("/robot")
async def websocket_robot_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for NVIDIA JetBot or Simulator client.
    Handles bi-directional telemetry, robot events, and downstream motor/patrol commands.
    """
    await manager.connect_robot(websocket)
    db = SessionLocal()
    try:
        # Acknowledge connection
        await websocket.send_text(json.dumps({
            "action": "CONNECTED",
            "message": "Connected to The Patrol Jetbot Backend Service"
        }))

        while True:
            raw_data = await websocket.receive_text()
            try:
                msg = json.loads(raw_data)
            except Exception:
                continue

            msg_type = msg.get("type", "")
            data = msg.get("data", {})

            if msg_type == "TELEMETRY":
                telemetry_obj = RobotTelemetry(**data)
                await robot_service.update_telemetry(db, telemetry_obj)

            elif msg_type == "SECURITY_EVENT":
                event_create = SecurityEventCreate(**data)
                await event_service.record_event(db, event_create)

            elif msg_type == "PATROL_PROGRESS":
                session_id = data.get("session_id")
                if session_id:
                    progress_obj = PatrolProgressUpdate(
                        current_checkpoint_idx=data.get("current_checkpoint_idx", 0),
                        progress_percent=data.get("progress_percent", 0.0),
                        status=data.get("status")
                    )
                    await patrol_service.update_progress(db, session_id, progress_obj)

            elif msg_type == "HEARTBEAT":
                robot_service.last_heartbeat = robot_service.last_heartbeat
                await websocket.send_text(json.dumps({"action": "HEARTBEAT_ACK"}))

    except WebSocketDisconnect:
        manager.disconnect_robot(websocket)
        logger.info("JetBot disconnected from WebSocket")
    except Exception as e:
        logger.error(f"Error in robot websocket loop: {e}")
        manager.disconnect_robot(websocket)
    finally:
        db.close()

@router.websocket("/web")
async def websocket_web_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for Frontend Monitoring Dashboards.
    Receives real-time telemetry, alerts, and patrol updates. Can send manual teleop controls.
    """
    await manager.connect_web(websocket)
    db = SessionLocal()
    try:
        # Send initial robot state
        current_status = robot_service.get_status().model_dump(mode="json")
        await websocket.send_text(json.dumps({
            "type": "INITIAL_STATE",
            "data": {
                "robot": current_status,
                "is_robot_connected": manager.is_robot_connected()
            }
        }))

        while True:
            raw_data = await websocket.receive_text()
            try:
                msg = json.loads(raw_data)
            except Exception:
                continue

            action = msg.get("action", "")
            if action == "TELEOP":
                cmd = TeleopCommand(
                    command=msg.get("command", "STOP"),
                    linear_speed=msg.get("linear_speed"),
                    angular_speed=msg.get("angular_speed"),
                    duration=msg.get("duration")
                )
                await robot_service.handle_teleop_command(db, cmd)

            elif action == "EMERGENCY_STOP":
                reason = msg.get("reason", "Operator emergency stop from web dashboard")
                await robot_service.trigger_emergency_stop(db, reason)

            elif action == "PING":
                await websocket.send_text(json.dumps({"type": "PONG"}))

    except WebSocketDisconnect:
        manager.disconnect_web(websocket)
    except Exception as e:
        logger.error(f"Error in web websocket loop: {e}")
        manager.disconnect_web(websocket)
    finally:
        db.close()

@router.websocket("/video")
async def websocket_video_endpoint(websocket: WebSocket):
    """
    Binary WebSocket endpoint for high-speed camera frame streaming.
    """
    await websocket.accept()
    try:
        while True:
            # Accepts binary JPEG frame from robot or simulator
            frame_bytes = await websocket.receive_bytes()
            video_streamer.update_frame(frame_bytes)
    except WebSocketDisconnect:
        logger.info("Video WebSocket client disconnected")
    except Exception as e:
        logger.error(f"Error in video websocket: {e}")
