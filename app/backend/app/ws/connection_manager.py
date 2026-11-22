"""WebSocket connection manager for JetBot, Web UI clients, and teleop dead-man repeater."""

import asyncio
import contextlib
import json
import logging
import time
from typing import Optional, Set, Tuple

from fastapi import WebSocket

from app.config import settings
from app.db.base import utc_now

logger = logging.getLogger("ws_manager")


class ConnectionManager:
    """Manages active WebSocket sessions and command forwarding between Web and JetBot."""

    def __init__(self) -> None:
        self.web_clients: Set[WebSocket] = set()
        self.robot_client: Optional[WebSocket] = None
        self.latest_frame_b64: Optional[str] = None
        self._teleop_task: Optional[asyncio.Task] = None
        self._teleop_cmd: Tuple[float, float] = (0.0, 0.0)
        self._teleop_last_refresh: float = 0.0

    def reset(self) -> None:
        """Reset all in-memory WebSocket state (used between automated tests)."""
        if self._teleop_task is not None and not self._teleop_task.done():
            self._teleop_task.cancel()
        self._teleop_task = None
        self._teleop_cmd = (0.0, 0.0)
        self._teleop_last_refresh = 0.0
        self.web_clients.clear()
        self.robot_client = None
        self.latest_frame_b64 = None

    async def connect_web(self, websocket: WebSocket) -> None:
        """Accept and register a Web dashboard client."""
        await websocket.accept()
        self.web_clients.add(websocket)
        logger.info("Web client connected. Total: %d", len(self.web_clients))

    def disconnect_web(self, websocket: WebSocket) -> None:
        """Unregister a Web dashboard client."""
        self.web_clients.discard(websocket)
        logger.info("Web client disconnected. Total: %d", len(self.web_clients))

    async def connect_robot(self, websocket: WebSocket) -> None:
        """Accept and register the active JetBot WebSocket connection."""
        await websocket.accept()
        self.robot_client = websocket
        logger.info("JetBot connected to WebSocket Hub!")

    def disconnect_robot(self) -> None:
        """Clear the JetBot connection and cancel any active teleop repeater."""
        self.robot_client = None
        if self._teleop_task is not None and not self._teleop_task.done():
            self._teleop_task.cancel()
        self._teleop_task = None
        logger.warning("JetBot disconnected from WebSocket Hub!")

    async def broadcast_to_web(self, message: dict) -> None:
        """Broadcast a JSON message to all connected Web clients, pruning dead sockets."""
        # [PENDING_INTEGRATION: FRONTEND_WS_TOPICS]
        # Hiện tại: Phát toàn bộ payload JSON (telemetry, event, alert, system, frame) tới các Web client.
        # Cần khớp: Định dạng envelope và tên trường hiển thị với Frontend.
        # Hành động: Chuẩn hóa key envelope tại đây nếu Frontend cần cấu trúc wrapper riêng.
        payload = json.dumps(message, default=str)
        for client in list(self.web_clients):
            try:
                await client.send_text(payload)
            except Exception:
                self.web_clients.discard(client)

    async def send_to_robot(self, message: dict) -> bool:
        """Send a JSON command to the connected JetBot; return True if dispatched."""
        if self.robot_client is None:
            logger.warning("Lệnh bị bỏ qua: JetBot chưa kết nối!")
            return False
        try:
            await self.robot_client.send_text(json.dumps(message, default=str))
            return True
        except Exception as exc:
            logger.warning("Không thể gửi lệnh tới JetBot: %s", exc)
            return False

    async def _teleop_repeater(self) -> None:
        interval = max(0.05, settings.TELEOP_REPEAT_INTERVAL_MS / 1000.0)
        try:
            while self.robot_client is not None:
                await asyncio.sleep(interval)
                if (time.monotonic() - self._teleop_last_refresh) > settings.TELEOP_HOLD_TIMEOUT_S:
                    await self.send_to_robot(
                        {"cmd": "stop", "timestamp": utc_now().isoformat()}
                    )
                    break
                left, right = self._teleop_cmd
                await self.send_to_robot(
                    {
                        "cmd": "move",
                        "left": left,
                        "right": right,
                        "timestamp": utc_now().isoformat(),
                    }
                )
        except asyncio.CancelledError:
            raise

    async def stop_teleop(self) -> None:
        """Cancel any active teleop repeat loop."""
        if self._teleop_task is not None and not self._teleop_task.done():
            self._teleop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._teleop_task
        self._teleop_task = None
        self._teleop_cmd = (0.0, 0.0)

    # [PENDING_INTEGRATION: KIET_DEADMAN_WATCHDOG]
    # Hiện tại: Chuyển tiếp ngay lệnh move và hỗ trợ lặp lại 200ms (5Hz) khi hold=True để giữ watchdog 1s của JetBot.
    # Cần khớp: Chốt với Kiệt chu kỳ watchdog (hiện robot/src/safety/safety.py dùng cmd_timeout=1.0s) và quy ước hold của Web.
    # Hành động: Điều chỉnh TELEOP_REPEAT_INTERVAL_MS / TELEOP_HOLD_TIMEOUT_S trong config.py khi thử trên robot thật.
    async def forward_teleop_cmd(
        self,
        left: float,
        right: float,
        hold: bool = False,
    ) -> bool:
        """Forward a normalized left/right motor command to JetBot, optionally keeping it alive at 5Hz."""
        clamped_left = max(-1.0, min(1.0, float(left)))
        clamped_right = max(-1.0, min(1.0, float(right)))
        cmd = {
            "cmd": "move",
            "left": clamped_left,
            "right": clamped_right,
            "timestamp": utc_now().isoformat(),
        }
        sent = await self.send_to_robot(cmd)

        if clamped_left == 0.0 and clamped_right == 0.0:
            await self.stop_teleop()
            return sent

        if hold:
            self._teleop_cmd = (clamped_left, clamped_right)
            self._teleop_last_refresh = time.monotonic()
            if self._teleop_task is None or self._teleop_task.done():
                self._teleop_task = asyncio.create_task(self._teleop_repeater())
        else:
            await self.stop_teleop()
        return sent

    async def send_emergency_stop(self) -> bool:
        """Immediately halt any teleop loop and dispatch high-priority emergency stop."""
        await self.stop_teleop()
        return await self.send_to_robot(
            {
                "cmd": "emergency_stop",
                "priority": "HIGH",
                "timestamp": utc_now().isoformat(),
            }
        )


manager = ConnectionManager()
