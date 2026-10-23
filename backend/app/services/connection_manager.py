import json
import logging
from typing import Set, Dict, Any, Optional
from fastapi import WebSocket

logger = logging.getLogger("patrol_jetbot.ws")

class ConnectionManager:
    """
    Manages WebSocket connections between JetBot robot and Web Frontend clients.
    """
    def __init__(self):
        self.robot_connections: Set[WebSocket] = set()
        self.web_connections: Set[WebSocket] = set()
        self.video_subscribers: Set[WebSocket] = set()

    async def connect_robot(self, websocket: WebSocket):
        await websocket.accept()
        self.robot_connections.add(websocket)
        logger.info(f"Robot connected via WebSocket: {websocket.client}")

    def disconnect_robot(self, websocket: WebSocket):
        if websocket in self.robot_connections:
            self.robot_connections.remove(websocket)
            logger.info("Robot disconnected from WebSocket")

    def is_robot_connected(self) -> bool:
        return len(self.robot_connections) > 0

    async def connect_web(self, websocket: WebSocket):
        await websocket.accept()
        self.web_connections.add(websocket)
        logger.info(f"Web client connected. Total clients: {len(self.web_connections)}")

    def disconnect_web(self, websocket: WebSocket):
        if websocket in self.web_connections:
            self.web_connections.remove(websocket)
            logger.info(f"Web client disconnected. Total clients: {len(self.web_connections)}")

    async def send_to_robot(self, data: Dict[str, Any]) -> bool:
        """Send message/command downstream to connected JetBot(s)"""
        if not self.robot_connections:
            logger.warning("No robot connected to receive message")
            return False

        message = json.dumps(data)
        disconnected = set()
        for ws in self.robot_connections:
            try:
                await ws.send_text(message)
            except Exception as e:
                logger.error(f"Error sending to robot: {e}")
                disconnected.add(ws)

        for ws in disconnected:
            self.disconnect_robot(ws)

        return True

    async def broadcast_to_web(self, event_type: str, data: Any):
        """Broadcast event/telemetry upstream to all connected Web dashboards"""
        if not self.web_connections:
            return

        payload = json.dumps({
            "type": event_type,
            "data": data
        })

        disconnected = set()
        for ws in self.web_connections:
            try:
                await ws.send_text(payload)
            except Exception as e:
                logger.debug(f"Error broadcasting to web client: {e}")
                disconnected.add(ws)

        for ws in disconnected:
            self.disconnect_web(ws)

manager = ConnectionManager()
