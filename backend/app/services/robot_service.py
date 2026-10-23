import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.models.robot import RobotState
from app.models.event import RobotLog
from app.schemas.teleop import TeleopCommand, TeleopResponse
from app.schemas.robot import RobotTelemetry, RobotStatusResponse
from app.services.connection_manager import manager

logger = logging.getLogger("patrol_jetbot.robot")

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class RobotService:
    def __init__(self):
        # In-memory fast cache
        self.robot_id = "jetbot_01"
        self.current_mode = "IDLE"
        self.battery_percentage = 100.0
        self.battery_voltage = 12.4
        self.wifi_rssi = -50
        self.linear_speed = 0.0
        self.angular_speed = 0.0
        self.current_x = 0.0
        self.current_y = 0.0
        self.current_heading = 0.0
        self.active_route_id: Optional[str] = None
        self.active_session_id: Optional[str] = None
        self.last_heartbeat = utc_now()

    def get_or_create_state_record(self, db: Session) -> RobotState:
        record = db.query(RobotState).filter(RobotState.robot_id == self.robot_id).first()
        if not record:
            record = RobotState(robot_id=self.robot_id)
            db.add(record)
            db.commit()
            db.refresh(record)
        return record

    async def update_telemetry(self, db: Session, telemetry: RobotTelemetry) -> RobotStatusResponse:
        """Update robot telemetry from upstream robot/simulator message"""
        self.last_heartbeat = utc_now()
        if telemetry.current_mode:
            self.current_mode = telemetry.current_mode
        if telemetry.battery_percentage is not None:
            self.battery_percentage = telemetry.battery_percentage
        if telemetry.battery_voltage is not None:
            self.battery_voltage = telemetry.battery_voltage
        if telemetry.wifi_rssi is not None:
            self.wifi_rssi = telemetry.wifi_rssi
        if telemetry.linear_speed is not None:
            self.linear_speed = telemetry.linear_speed
        if telemetry.angular_speed is not None:
            self.angular_speed = telemetry.angular_speed
        if telemetry.current_x is not None:
            self.current_x = telemetry.current_x
        if telemetry.current_y is not None:
            self.current_y = telemetry.current_y
        if telemetry.current_heading is not None:
            self.current_heading = telemetry.current_heading
        if telemetry.active_route_id is not None:
            self.active_route_id = telemetry.active_route_id
        if telemetry.active_session_id is not None:
            self.active_session_id = telemetry.active_session_id

        # Update DB record
        record = self.get_or_create_state_record(db)
        record.connection_status = "CONNECTED"
        record.current_mode = self.current_mode
        record.battery_percentage = self.battery_percentage
        record.battery_voltage = self.battery_voltage
        record.wifi_rssi = self.wifi_rssi
        record.linear_speed = self.linear_speed
        record.angular_speed = self.angular_speed
        record.current_x = self.current_x
        record.current_y = self.current_y
        record.current_heading = self.current_heading
        record.active_route_id = self.active_route_id
        record.active_session_id = self.active_session_id
        record.last_heartbeat = self.last_heartbeat
        db.commit()

        # Broadcast telemetry to web clients
        status = self.get_status()
        await manager.broadcast_to_web("TELEMETRY", status.model_dump(mode="json"))
        return status

    def get_status(self) -> RobotStatusResponse:
        now = utc_now()
        # Ensure comparison between aware or naive
        dt_seconds = (now.timestamp() - self.last_heartbeat.timestamp())
        is_alive = manager.is_robot_connected() or (dt_seconds < settings.ROBOT_HEARTBEAT_TIMEOUT)
        
        return RobotStatusResponse(
            robot_id=self.robot_id,
            connection_status="CONNECTED" if is_alive else "DISCONNECTED",
            current_mode=self.current_mode if is_alive else "OFFLINE",
            battery_percentage=self.battery_percentage,
            battery_voltage=self.battery_voltage,
            wifi_rssi=self.wifi_rssi,
            linear_speed=self.linear_speed,
            angular_speed=self.angular_speed,
            current_x=self.current_x,
            current_y=self.current_y,
            current_heading=self.current_heading,
            active_route_id=self.active_route_id,
            active_session_id=self.active_session_id,
            is_online=is_alive,
            last_heartbeat=self.last_heartbeat,
            updated_at=now
        )

    async def handle_teleop_command(self, db: Session, cmd: TeleopCommand) -> TeleopResponse:
        """Process manual control command from Web App and dispatch to Robot"""
        lin_speed = cmd.linear_speed if cmd.linear_speed is not None else settings.DEFAULT_LINEAR_SPEED
        ang_speed = cmd.angular_speed if cmd.angular_speed is not None else settings.DEFAULT_ANGULAR_SPEED

        # Command translation to target velocities
        applied_linear = 0.0
        applied_angular = 0.0

        if cmd.command == "FORWARD":
            applied_linear = lin_speed
            applied_angular = 0.0
            if self.current_mode not in ["TEACH", "REPEAT"]:
                self.current_mode = "MANUAL"
        elif cmd.command == "BACKWARD":
            applied_linear = -lin_speed
            applied_angular = 0.0
            if self.current_mode not in ["TEACH", "REPEAT"]:
                self.current_mode = "MANUAL"
        elif cmd.command == "LEFT":
            applied_linear = 0.0
            applied_angular = ang_speed
            if self.current_mode not in ["TEACH", "REPEAT"]:
                self.current_mode = "MANUAL"
        elif cmd.command == "RIGHT":
            applied_linear = 0.0
            applied_angular = -ang_speed
            if self.current_mode not in ["TEACH", "REPEAT"]:
                self.current_mode = "MANUAL"
        elif cmd.command == "STOP":
            applied_linear = 0.0
            applied_angular = 0.0
            if self.current_mode == "MANUAL":
                self.current_mode = "IDLE"
        elif cmd.command == "EMERGENCY_STOP":
            return await self.trigger_emergency_stop(db, "Emergency stop requested via teleop")

        self.linear_speed = applied_linear
        self.angular_speed = applied_angular

        # Send command down to JetBot over WebSocket
        payload = {
            "action": "TELEOP",
            "command": cmd.command,
            "linear_speed": applied_linear,
            "angular_speed": applied_angular,
            "duration": cmd.duration
        }
        await manager.send_to_robot(payload)

        # Notify web dashboards of teleop action
        await manager.broadcast_to_web("TELEOP_COMMAND", payload)

        return TeleopResponse(
            success=True,
            message=f"Command {cmd.command} dispatched successfully",
            robot_mode=self.current_mode,
            applied_linear=applied_linear,
            applied_angular=applied_angular
        )

    async def trigger_emergency_stop(self, db: Session, reason: str = "Emergency stop") -> TeleopResponse:
        """Immediately stops the robot, updates state to EMERGENCY_STOP, logs event"""
        self.linear_speed = 0.0
        self.angular_speed = 0.0
        self.current_mode = "EMERGENCY_STOP"

        payload = {
            "action": "EMERGENCY_STOP",
            "reason": reason
        }
        await manager.send_to_robot(payload)
        await manager.broadcast_to_web("EMERGENCY_STOP", payload)

        # Log to db
        log_entry = RobotLog(
            level="CRITICAL",
            source="TELEOP",
            message=f"EMERGENCY STOP TRIGGERED: {reason}"
        )
        db.add(log_entry)
        db.commit()

        logger.warning(f"EMERGENCY STOP TRIGGERED: {reason}")
        return TeleopResponse(
            success=True,
            message="Robot stopped in EMERGENCY_STOP state",
            robot_mode=self.current_mode,
            applied_linear=0.0,
            applied_angular=0.0
        )

robot_service = RobotService()
