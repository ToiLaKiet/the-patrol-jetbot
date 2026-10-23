import io
import time
import json
import math
import random
import asyncio
import logging
import base64
from typing import Optional, List, Dict, Any
from PIL import Image, ImageDraw, ImageFont
import httpx
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SIMULATOR] %(message)s")
logger = logging.getLogger("JetbotSimulator")

class JetBotSimulator:
    """
    Virtual NVIDIA JetBot simulator simulating:
    - Robot-server WebSocket communication
    - Live camera feed generation & streaming
    - Odometry & motor physics (Teach & Repeat)
    - Obstacle detection & Stop/Resume behavior
    - Person detection & security alert generation
    """
    def __init__(self, backend_url: str = "http://localhost:8000", ws_url: str = "ws://localhost:8000/ws/robot"):
        self.backend_url = backend_url
        self.ws_url = ws_url
        self.robot_id = "jetbot_01"

        # Robot state
        self.mode = "IDLE"  # IDLE, MANUAL, TEACH, REPEAT, BLOCKED, EMERGENCY_STOP
        self.battery = 98.5
        self.voltage = 12.3
        self.wifi_rssi = -48

        # Pose & Motion
        self.x = 0.0
        self.y = 0.0
        self.theta = 0.0  # radians
        self.linear_speed = 0.0
        self.angular_speed = 0.0

        # Teach Mode state
        self.active_teach_route_id: Optional[str] = None
        self.teach_sequence_idx = 0
        self.teach_start_time = 0.0

        # Repeat Mode state
        self.active_patrol_session_id: Optional[str] = None
        self.patrol_checkpoints: List[Dict[str, Any]] = []
        self.current_patrol_idx = 0
        self.patrol_paused = False

        # Obstacle state
        self.is_blocked = False

        self.running = False
        self.ws: Optional[websockets.WebSocketClientProtocol] = None

    def generate_camera_frame(self, person_detected: bool = False, obstacle_detected: bool = False) -> bytes:
        """Draws synthetic camera frame with dynamic visual markers, timestamp, and robot HUD"""
        w, h = 640, 480
        img = Image.new("RGB", (w, h), color=(18, 22, 30))
        draw = ImageDraw.Draw(img)

        # Draw indoor perspective floor lines
        horizon = 220
        draw.line([0, horizon, w, horizon], fill=(45, 55, 72), width=1)
        for i in range(-5, 6):
            start_x = w // 2 + i * 40
            end_x = w // 2 + i * 160
            draw.line([start_x, horizon, end_x, h], fill=(30, 41, 59), width=1)

        # Draw simulated walls / corridor
        draw.polygon([(0, 0), (80, horizon), (0, horizon)], fill=(26, 32, 44))
        draw.polygon([(w, 0), (w - 80, horizon), (w, horizon)], fill=(26, 32, 44))

        # Simulated person if detected
        if person_detected:
            # Draw person silhouette / bounding box
            px, py, pw, ph = 260, 160, 110, 240
            draw.rectangle([px, py, px + pw, py + ph], outline=(239, 68, 68), width=3)
            draw.text((px, py - 20), "PERSON 94.8%", fill=(239, 68, 68))
            # Head & body silhouette
            draw.ellipse([px + 35, py + 15, px + 75, py + 65], fill=(185, 28, 28))
            draw.rectangle([px + 25, py + 65, px + 85, py + 180], fill=(153, 27, 27))
            draw.line([px + 40, py + 180, px + 40, py + 235], fill=(153, 27, 27), width=8)
            draw.line([px + 70, py + 180, px + 70, py + 235], fill=(153, 27, 27), width=8)

        # Simulated obstacle if detected
        if obstacle_detected:
            ox, oy, ow, oh = 250, 290, 140, 100
            draw.rectangle([ox, oy, ox + ow, oy + oh], fill=(217, 119, 6), outline=(245, 158, 11), width=3)
            draw.text((ox + 15, oy + 35), "OBSTACLE (0.35m)", fill=(255, 255, 255))

        # HUD Overlay
        draw.rectangle([10, 10, w - 10, 40], fill=(15, 23, 42))
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S")
        hud_text = f"JETBOT SIMULATOR | {ts_str} | MODE: {self.mode} | BATT: {self.battery:.1f}% | X: {self.x:.2f}m Y: {self.y:.2f}m"
        draw.text((20, 18), hud_text, fill=(56, 189, 248))

        # Crosshairs in center
        cx, cy = w // 2, h // 2
        draw.line([cx - 20, cy, cx + 20, cy], fill=(148, 163, 184), width=1)
        draw.line([cx, cy - 20, cx, cy + 20], fill=(148, 163, 184), width=1)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()

    async def stream_frames_loop(self):
        """Continuously streams simulated video frames to backend"""
        async with httpx.AsyncClient() as client:
            while self.running:
                try:
                    frame = self.generate_camera_frame(
                        obstacle_detected=self.is_blocked
                    )
                    await client.post(
                        f"{self.backend_url}/api/v1/video/frame",
                        content=frame,
                        headers={"Content-Type": "image/jpeg"},
                        timeout=1.0
                    )
                except Exception as e:
                    pass
                await asyncio.sleep(0.08) # ~12 fps

    async def telemetry_loop(self):
        """Sends periodic telemetry to backend over WebSocket"""
        while self.running:
            if self.ws:
                # Physics step
                dt = 0.2
                if self.mode in ["MANUAL", "REPEAT"] and not self.is_blocked:
                    self.theta += self.angular_speed * dt
                    self.x += self.linear_speed * math.cos(self.theta) * dt
                    self.y += self.linear_speed * math.sin(self.theta) * dt
                    self.battery = max(10.0, self.battery - 0.002)

                telemetry = {
                    "type": "TELEMETRY",
                    "data": {
                        "robot_id": self.robot_id,
                        "connection_status": "CONNECTED",
                        "current_mode": self.mode,
                        "battery_percentage": round(self.battery, 1),
                        "battery_voltage": round(self.voltage, 2),
                        "wifi_rssi": self.wifi_rssi,
                        "linear_speed": round(self.linear_speed, 2),
                        "angular_speed": round(self.angular_speed, 2),
                        "current_x": round(self.x, 2),
                        "current_y": round(self.y, 2),
                        "current_heading": round(self.theta, 3),
                        "active_route_id": self.active_teach_route_id,
                        "active_session_id": self.active_patrol_session_id
                    }
                }
                try:
                    await self.ws.send(json.dumps(telemetry))
                except Exception as e:
                    logger.debug(f"Telemetry send error: {e}")
            await asyncio.sleep(0.2)

    async def repeat_patrol_loop(self):
        """Simulates autonomous repeat patrol following route checkpoints"""
        while self.running:
            if self.mode == "REPEAT" and not self.patrol_paused and not self.is_blocked and self.patrol_checkpoints:
                if self.current_patrol_idx < len(self.patrol_checkpoints):
                    target_cp = self.patrol_checkpoints[self.current_patrol_idx]
                    target_x = target_cp.get("x", 0.0)
                    target_y = target_cp.get("y", 0.0)

                    # Move robot toward target checkpoint
                    dx = target_x - self.x
                    dy = target_y - self.y
                    dist = math.sqrt(dx*dx + dy*dy)

                    if dist < 0.15 or len(self.patrol_checkpoints) == 1:
                        # Reached checkpoint
                        self.current_patrol_idx += 1
                        pct = (self.current_patrol_idx / len(self.patrol_checkpoints)) * 100.0
                        logger.info(f"Reached Checkpoint {self.current_patrol_idx}/{len(self.patrol_checkpoints)} ({pct:.1f}%)")

                        if self.ws and self.active_patrol_session_id:
                            progress_msg = {
                                "type": "PATROL_PROGRESS",
                                "data": {
                                    "session_id": self.active_patrol_session_id,
                                    "current_checkpoint_idx": self.current_patrol_idx,
                                    "progress_percent": round(pct, 1),
                                    "status": "COMPLETED" if self.current_patrol_idx >= len(self.patrol_checkpoints) else "RUNNING"
                                }
                            }
                            await self.ws.send(json.dumps(progress_msg))

                        if self.current_patrol_idx >= len(self.patrol_checkpoints):
                            logger.info("Patrol route successfully completed!")
                            self.mode = "IDLE"
                            self.linear_speed = 0.0
                            self.angular_speed = 0.0
                            self.active_patrol_session_id = None
                    else:
                        target_angle = math.atan2(dy, dx)
                        angle_diff = (target_angle - self.theta + math.pi) % (2 * math.pi) - math.pi
                        self.angular_speed = max(-0.8, min(0.8, angle_diff * 1.5))
                        self.linear_speed = 0.3
                else:
                    self.mode = "IDLE"
            await asyncio.sleep(0.3)

    async def trigger_person_detection(self):
        """Simulates Computer Vision person detection event with snapshot upload"""
        logger.info("TRIGGERING SIMULATED PERSON DETECTION EVENT...")
        frame_bytes = self.generate_camera_frame(person_detected=True)
        img_b64 = base64.b64encode(frame_bytes).decode("utf-8")

        event_payload = {
            "type": "SECURITY_EVENT",
            "data": {
                "event_type": "PERSON_DETECTED",
                "severity": "CRITICAL",
                "session_id": self.active_patrol_session_id,
                "confidence": 0.948,
                "bounding_box": json.dumps([160, 260, 400, 370]),
                "description": "Tuấn Anh Vision Module: Phát hiện người trong khu vực tuần tra (Camera RGB)",
                "image_base64": img_b64
            }
        }
        if self.ws:
            await self.ws.send(json.dumps(event_payload))
            logger.info("Person detection event sent to backend!")

    async def trigger_obstacle_stop_and_resume(self, block_duration: float = 3.5):
        """Simulates Obstacle detection -> stop -> wait -> resume"""
        logger.info("TRIGGERING SIMULATED OBSTACLE (STOP & RESUME)...")
        self.is_blocked = True
        prev_linear = self.linear_speed
        self.linear_speed = 0.0
        self.angular_speed = 0.0

        # Send OBSTACLE_BLOCKED event
        frame_bytes = self.generate_camera_frame(obstacle_detected=True)
        img_b64 = base64.b64encode(frame_bytes).decode("utf-8")

        blocked_payload = {
            "type": "SECURITY_EVENT",
            "data": {
                "event_type": "OBSTACLE_BLOCKED",
                "severity": "WARNING",
                "session_id": self.active_patrol_session_id,
                "confidence": 0.92,
                "description": "Vật cản xuất hiện phía trước (0.35m). JetBot chuyển trạng thái BLOCKED và dừng xe.",
                "image_base64": img_b64
            }
        }
        if self.ws:
            await self.ws.send(json.dumps(blocked_payload))

        # Wait while stopped
        await asyncio.sleep(block_duration)

        # Clear obstacle and resume
        self.is_blocked = False
        self.linear_speed = prev_linear
        logger.info("SIMULATED OBSTACLE REMOVED -> Resuming robot...")

        cleared_payload = {
            "type": "SECURITY_EVENT",
            "data": {
                "event_type": "OBSTACLE_CLEARED",
                "severity": "INFO",
                "session_id": self.active_patrol_session_id,
                "description": "Vật cản đã được dời đi. Tuyến đường thông thoáng ổn định, JetBot tiếp tục hành trình."
            }
        }
        if self.ws:
            await self.ws.send(json.dumps(cleared_payload))

    async def handle_downstream_message(self, msg: Dict[str, Any]):
        """Handles commands sent from Backend down to JetBot"""
        action = msg.get("action", "")

        if action == "TELEOP":
            cmd = msg.get("command")
            self.linear_speed = msg.get("linear_speed", 0.0)
            self.angular_speed = msg.get("angular_speed", 0.0)
            if self.mode not in ["TEACH", "REPEAT"]:
                self.mode = "MANUAL" if cmd != "STOP" else "IDLE"

            # If recording route in TEACH mode, automatically record checkpoint on movement
            if self.mode == "TEACH" and self.active_teach_route_id:
                await self._record_teach_checkpoint()

        elif action == "START_TEACH_MODE":
            self.mode = "TEACH"
            self.active_teach_route_id = msg.get("route_id")
            self.teach_sequence_idx = 0
            self.teach_start_time = time.time()
            self.x, self.y, self.theta = 0.0, 0.0, 0.0
            logger.info(f"Entered TEACH MODE for route: {self.active_teach_route_id}")
            # Record first initial checkpoint
            await self._record_teach_checkpoint()

        elif action == "STOP_TEACH_MODE":
            self.mode = "IDLE"
            self.active_teach_route_id = None
            self.linear_speed = 0.0
            self.angular_speed = 0.0
            logger.info("Exited TEACH MODE")

        elif action == "START_PATROL":
            self.mode = "REPEAT"
            self.active_patrol_session_id = msg.get("session_id")
            self.patrol_checkpoints = msg.get("checkpoints", [])
            self.current_patrol_idx = 0
            self.patrol_paused = False
            self.is_blocked = False
            # Start from initial checkpoint pose
            if self.patrol_checkpoints:
                self.x = self.patrol_checkpoints[0].get("x", 0.0)
                self.y = self.patrol_checkpoints[0].get("y", 0.0)
                self.theta = self.patrol_checkpoints[0].get("theta", 0.0)
            logger.info(f"Entered REPEAT MODE for session: {self.active_patrol_session_id} with {len(self.patrol_checkpoints)} checkpoints")

        elif action == "PAUSE_PATROL":
            self.patrol_paused = True
            self.linear_speed = 0.0
            self.angular_speed = 0.0
            logger.info("PATROL PAUSED")

        elif action == "RESUME_PATROL":
            self.patrol_paused = False
            logger.info("PATROL RESUMED")

        elif action == "STOP_PATROL" or action == "EMERGENCY_STOP":
            self.mode = "EMERGENCY_STOP" if action == "EMERGENCY_STOP" else "IDLE"
            self.linear_speed = 0.0
            self.angular_speed = 0.0
            self.active_patrol_session_id = None
            logger.warning(f"STOP ACTION: {action}")

    async def _record_teach_checkpoint(self):
        """Generates and uploads a checkpoint to the backend during Teach mode"""
        if not self.active_teach_route_id:
            return
        frame = self.generate_camera_frame()
        b64_frame = base64.b64encode(frame).decode("utf-8")
        offset = time.time() - self.teach_start_time

        cp_data = {
            "sequence_idx": self.teach_sequence_idx,
            "timestamp_offset": round(offset, 2),
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "theta": round(self.theta, 3),
            "linear_speed": round(self.linear_speed, 2),
            "angular_speed": round(self.angular_speed, 2),
            "keyframe_base64": b64_frame
        }
        self.teach_sequence_idx += 1

        async with httpx.AsyncClient() as client:
            try:
                await client.post(
                    f"{self.backend_url}/api/v1/routes/{self.active_teach_route_id}/checkpoints",
                    json=cp_data,
                    timeout=2.0
                )
            except Exception as e:
                logger.error(f"Error posting checkpoint to backend: {e}")

    async def run(self):
        """Main simulator loop connecting WebSocket and running background tasks"""
        self.running = True
        logger.info(f"Starting JetBot Simulator -> Connecting to {self.ws_url}...")

        while self.running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    self.ws = ws
                    logger.info("Connected to Backend WebSocket successfully!")

                    # Launch concurrent tasks
                    tasks = [
                        asyncio.create_task(self.stream_frames_loop()),
                        asyncio.create_task(self.telemetry_loop()),
                        asyncio.create_task(self.repeat_patrol_loop()),
                    ]

                    # Listen for messages from backend
                    async for message in ws:
                        try:
                            msg_dict = json.loads(message)
                            await self.handle_downstream_message(msg_dict)
                        except Exception as e:
                            logger.error(f"Error handling message: {e}")

                    for t in tasks:
                        t.cancel()

            except Exception as e:
                logger.warning(f"Connection lost ({e}). Reconnecting in 2s...")
                self.ws = None
                await asyncio.sleep(2.0)

if __name__ == "__main__":
    sim = JetBotSimulator()
    try:
        asyncio.run(sim.run())
    except KeyboardInterrupt:
        logger.info("Simulator terminated.")
