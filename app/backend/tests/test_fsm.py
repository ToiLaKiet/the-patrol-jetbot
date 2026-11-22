"""Unit tests for PatrolFSM command gating, match-score loss detection, and heartbeats."""

import time

from app.core.fsm import PatrolFSM, RobotState


def test_offline_rejects_normal_commands_but_allows_emergency_stop() -> None:
    machine = PatrolFSM()
    assert machine.state == RobotState.OFFLINE

    ok_move, reason_move = machine.validate_command("move")
    assert not ok_move
    assert "OFFLINE" in reason_move

    ok_patrol, _ = machine.validate_command("start_patrol")
    assert not ok_patrol

    ok_estop, _ = machine.validate_command("emergency_stop")
    assert ok_estop


def test_state_command_validation_matrix() -> None:
    machine = PatrolFSM()
    machine.on_robot_connected()
    assert machine.state == RobotState.IDLE

    assert machine.validate_command("start_teach")[0]
    assert machine.validate_command("start_patrol")[0]
    assert not machine.validate_command("end_teach")[0]
    assert not machine.validate_command("resume_patrol")[0]

    machine.apply_command_transition("start_teach")
    assert machine.state == RobotState.TEACHING
    assert machine.validate_command("move")[0]
    assert machine.validate_command("end_teach")[0]
    assert not machine.validate_command("start_patrol")[0]

    machine.apply_command_transition("end_teach")
    assert machine.state == RobotState.IDLE

    machine.apply_command_transition("start_patrol", route_id="r1", run_id="run1")
    assert machine.state == RobotState.PATROLLING
    assert machine.validate_command("pause_patrol")[0]
    assert not machine.validate_command("move")[0]
    assert not machine.validate_command("start_teach")[0]

    machine.apply_command_transition("pause_patrol")
    assert machine.state == RobotState.PAUSED
    assert machine.validate_command("resume_patrol")[0]
    assert machine.validate_command("emergency_stop")[0]


def test_consecutive_low_match_score_triggers_error_lost() -> None:
    machine = PatrolFSM()
    machine.on_robot_connected()
    machine.apply_command_transition("start_patrol", route_id="r1", run_id="run1")

    assert machine.update_from_telemetry(state="PATROLLING", match_score=0.20) is False
    assert machine.state == RobotState.PATROLLING
    assert machine.consecutive_low_match_count == 1

    # Recovery frame resets low-match streak
    assert machine.update_from_telemetry(state="PATROLLING", match_score=0.65) is False
    assert machine.consecutive_low_match_count == 0

    # Three consecutive low match scores trigger ERROR_LOST
    assert machine.update_from_telemetry(state="PATROLLING", match_score=0.30) is False
    assert machine.update_from_telemetry(state="PATROLLING", match_score=0.25) is False
    assert machine.update_from_telemetry(state="PATROLLING", match_score=0.10) is True
    assert machine.state == RobotState.ERROR_LOST


def test_heartbeat_expiration_check() -> None:
    machine = PatrolFSM()
    assert machine.is_heartbeat_expired() is False

    t0 = time.monotonic()
    machine.on_robot_connected()
    machine.touch_heartbeat(now_mono=t0)
    assert machine.is_heartbeat_expired(now_mono=t0 + 5.0, timeout_s=10.0) is False
    assert machine.is_heartbeat_expired(now_mono=t0 + 12.0, timeout_s=10.0) is True
