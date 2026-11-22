"""Finite State Machine managing JetBot operational states and match-score safety."""

from datetime import datetime
from enum import Enum
import time
from typing import Dict, Optional, Set, Tuple

from app.config import settings
from app.db.base import utc_now


class RobotState(str, Enum):
    """Canonical JetBot states tracked by the backend middleware."""

    OFFLINE = "OFFLINE"
    IDLE = "IDLE"
    TELEOP = "TELEOP"
    TEACHING = "TEACHING"
    PATROLLING = "PATROLLING"
    BLOCKED = "BLOCKED"
    PAUSED = "PAUSED"
    ERROR_LOST = "ERROR_LOST"


ALLOWED_COMMANDS_BY_STATE: Dict[RobotState, Set[str]] = {
    RobotState.OFFLINE: set(),
    RobotState.IDLE: {"move", "stop", "start_teach", "start_patrol"},
    RobotState.TELEOP: {"move", "stop", "start_teach", "start_patrol"},
    RobotState.TEACHING: {"move", "stop", "end_teach"},
    RobotState.PATROLLING: {"stop", "pause_patrol"},
    RobotState.BLOCKED: {"stop", "pause_patrol", "resume_patrol"},
    RobotState.PAUSED: {"stop", "resume_patrol"},
    RobotState.ERROR_LOST: {"stop", "move"},
}

KNOWN_COMMANDS: Set[str] = {
    "move",
    "stop",
    "emergency_stop",
    "start_teach",
    "end_teach",
    "start_patrol",
    "pause_patrol",
    "resume_patrol",
}


def parse_robot_state(raw_state: Optional[str]) -> Optional[RobotState]:
    """Parse external state names (including 'ERROR/LOST') into RobotState."""
    if not raw_state:
        return None
    normalized = raw_state.strip().upper().replace("/", "_")
    try:
        return RobotState(normalized)
    except ValueError:
        return None


class PatrolFSM:
    """Tracks live robot status, validates Web commands, and detects route loss."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Reset FSM to initial offline state (also used between unit tests)."""
        self.state: RobotState = RobotState.OFFLINE
        self.robot_connected: bool = False
        self.active_run_id: Optional[str] = None
        self.active_route_id: Optional[str] = None
        self.checkpoint_seq: Optional[int] = None
        self.total_checkpoints: Optional[int] = None
        self.match_score: Optional[float] = None
        self.battery_v: Optional[float] = None
        self.battery_pct: Optional[int] = None
        self.consecutive_low_match_count: int = 0
        self.disconnect_count: int = 0
        self.last_heartbeat_at: Optional[datetime] = None
        self._last_heartbeat_mono: Optional[float] = None
        self.last_updated_at: datetime = utc_now()

    def touch_heartbeat(self, now_mono: Optional[float] = None) -> None:
        """Record a fresh robot activity timestamp."""
        self.last_heartbeat_at = utc_now()
        self._last_heartbeat_mono = (
            now_mono if now_mono is not None else time.monotonic()
        )
        self.last_updated_at = self.last_heartbeat_at

    def on_robot_connected(self) -> None:
        """Transition from OFFLINE to IDLE when JetBot establishes /ws/robot."""
        self.robot_connected = True
        self.state = RobotState.IDLE
        self.consecutive_low_match_count = 0
        self.touch_heartbeat()

    def on_robot_disconnected(self) -> None:
        """Transition to OFFLINE and clear active telemetry streak on disconnect."""
        if self.robot_connected:
            self.disconnect_count += 1
        self.robot_connected = False
        self.state = RobotState.OFFLINE
        self.consecutive_low_match_count = 0
        self._last_heartbeat_mono = None
        self.last_updated_at = utc_now()

    def is_heartbeat_expired(
        self,
        now_mono: Optional[float] = None,
        timeout_s: Optional[float] = None,
    ) -> bool:
        """Return True if a connected robot exceeded the heartbeat timeout."""
        if not self.robot_connected or self._last_heartbeat_mono is None:
            return False
        current = now_mono if now_mono is not None else time.monotonic()
        limit = timeout_s if timeout_s is not None else settings.HEARTBEAT_TIMEOUT_S
        return (current - self._last_heartbeat_mono) > limit

    def validate_command(self, cmd: str) -> Tuple[bool, str]:
        """Validate whether a normalized Web command is allowed in the current state."""
        if cmd not in KNOWN_COMMANDS:
            return False, f"Lệnh không hợp lệ: {cmd}"
        # Emergency stop always bypasses state checks and queues.
        if cmd == "emergency_stop":
            return True, "OK"
        if not self.robot_connected or self.state == RobotState.OFFLINE:
            return False, "JetBot chưa kết nối (OFFLINE)"
        allowed = ALLOWED_COMMANDS_BY_STATE.get(self.state, set())
        if cmd not in allowed:
            return (
                False,
                f"Lệnh '{cmd}' không hợp lệ khi robot đang ở trạng thái {self.state.value}",
            )
        return True, "OK"

    def apply_command_transition(
        self,
        cmd: str,
        route_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> None:
        """Update optimistic FSM state when a valid Web command is forwarded."""
        if cmd == "emergency_stop" or cmd == "stop":
            if self.robot_connected:
                self.state = RobotState.IDLE
            self.consecutive_low_match_count = 0
        elif cmd == "move":
            if self.state == RobotState.IDLE:
                self.state = RobotState.TELEOP
        elif cmd == "start_teach":
            self.state = RobotState.TEACHING
            self.consecutive_low_match_count = 0
        elif cmd == "end_teach":
            self.state = RobotState.IDLE
        elif cmd == "start_patrol":
            self.state = RobotState.PATROLLING
            self.consecutive_low_match_count = 0
            if route_id is not None:
                self.active_route_id = route_id
            if run_id is not None:
                self.active_run_id = run_id
        elif cmd == "pause_patrol":
            self.state = RobotState.PAUSED
        elif cmd == "resume_patrol":
            self.state = RobotState.PATROLLING
        self.last_updated_at = utc_now()

    def evaluate_match_score(self, match_score: Optional[float]) -> bool:
        """Detect consecutive low visual match scores while patrolling and trigger ERROR_LOST."""
        # [PENDING_INTEGRATION: TUANANH_MATCH_SCORE]
        # Hiện tại: Ngưỡng match_score < 0.35 liên tiếp trong 3 checkpoint khi PATROLLING sẽ chuyển ERROR_LOST.
        # Cần khớp: Tuấn Anh chốt ngưỡng điểm match keyframe và số tick liên tiếp thực tế.
        # Hành động: Điều chỉnh MATCH_SCORE_THRESHOLD / MATCH_SCORE_LOST_STREAK trong config.py hoặc .env.
        if self.state != RobotState.PATROLLING or match_score is None:
            return False

        if match_score < settings.MATCH_SCORE_THRESHOLD:
            self.consecutive_low_match_count += 1
            if self.consecutive_low_match_count >= settings.MATCH_SCORE_LOST_STREAK:
                self.state = RobotState.ERROR_LOST
                self.last_updated_at = utc_now()
                return True
        else:
            self.consecutive_low_match_count = 0
        return False

    def update_from_telemetry(
        self,
        *,
        state: Optional[str] = None,
        checkpoint_seq: Optional[int] = None,
        total_checkpoints: Optional[int] = None,
        match_score: Optional[float] = None,
        battery_v: Optional[float] = None,
        battery_pct: Optional[int] = None,
        run_id: Optional[str] = None,
    ) -> bool:
        """Synchronize FSM metrics from an incoming telemetry frame; return True if ERROR_LOST fired."""
        parsed = parse_robot_state(state)
        if parsed is not None:
            self.state = parsed
            if parsed != RobotState.PATROLLING:
                self.consecutive_low_match_count = 0

        if checkpoint_seq is not None:
            self.checkpoint_seq = checkpoint_seq
        if total_checkpoints is not None:
            self.total_checkpoints = total_checkpoints
        if match_score is not None:
            self.match_score = match_score
        if battery_v is not None:
            self.battery_v = battery_v
        if battery_pct is not None:
            self.battery_pct = battery_pct
        if run_id is not None:
            self.active_run_id = run_id

        self.touch_heartbeat()
        return self.evaluate_match_score(match_score)

    def get_snapshot(self) -> dict:
        """Return JSON-serializable snapshot of live robot and patrol state."""
        return {
            "state": self.state.value,
            "robot_connected": self.robot_connected,
            "active_run_id": self.active_run_id,
            "active_route_id": self.active_route_id,
            "checkpoint_seq": self.checkpoint_seq,
            "total_checkpoints": self.total_checkpoints,
            "match_score": self.match_score,
            "battery_v": self.battery_v,
            "battery_pct": self.battery_pct,
            "consecutive_low_match_count": self.consecutive_low_match_count,
            "disconnect_count": self.disconnect_count,
            "last_heartbeat_at": (
                self.last_heartbeat_at.isoformat() if self.last_heartbeat_at else None
            ),
            "last_updated_at": self.last_updated_at.isoformat(),
        }


fsm = PatrolFSM()
