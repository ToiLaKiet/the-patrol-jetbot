"""WebSocket endpoints (/ws/robot and /ws/web) coordinating JetBot, DB, FSM, and Web UI."""

from datetime import datetime, timezone
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.config import settings
from app.core.fsm import RobotState, fsm, parse_robot_state
from app.db.base import utc_now
from app.db.session import get_db
from app.models.event import SecurityEvent
from app.models.patrol import PatrolRun, RunTelemetry
from app.schemas.ws_schema import normalize_web_command
from app.services.notifier import notifier, save_evidence_base64
from app.ws.connection_manager import manager

ws_router = APIRouter(tags=["WebSocket"])
logger = logging.getLogger("ws_router")


def _compute_latency_ms(ts_raw: Optional[str]) -> Optional[float]:
    """Compute non-negative latency in ms from an ISO-8601 timestamp string."""
    if not ts_raw or not isinstance(ts_raw, str):
        return None
    try:
        cleaned = ts_raw.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        delta_ms = (utc_now() - parsed).total_seconds() * 1000.0
        return round(max(0.0, delta_ms), 2)
    except ValueError:
        return None


@ws_router.websocket("/ws/robot")
async def websocket_robot_endpoint(
    websocket: WebSocket,
    db: Session = Depends(get_db),
) -> None:
    """Bi-directional WebSocket channel used by JetBot to push telemetry/events and receive commands."""
    await manager.connect_robot(websocket)
    fsm.on_robot_connected()
    await manager.broadcast_to_web(
        {
            "type": "system",
            "state": fsm.state.value,
            "robot_connected": True,
            "message": "JetBot đã kết nối!",
            "timestamp": utc_now().isoformat(),
        }
    )

    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"type": "error", "message": "Payload JSON không hợp lệ"})
                )
                continue

            if not isinstance(data, dict):
                continue

            msg_type = str(data.get("type", "telemetry")).strip().lower()

            if msg_type == "telemetry":
                # [PENDING_INTEGRATION: KIET_BATTERY_INA219]
                # Hiện tại: Đọc `battery_v` (float) và `battery_pct` (int), tự động cảnh báo khi < 10.2V.
                # Cần khớp: Kiệt xác nhận tên trường và công thức quy đổi điện áp từ cảm biến INA219 trên I2C.
                # Hành động: Cập nhật key đọc dữ liệu pin và ngưỡng BATTERY_LOW_VOLTAGE khi ghép cảm biến thật.
                raw_bv = data.get("battery_v")
                raw_bp = data.get("battery_pct")
                battery_v = float(raw_bv) if raw_bv is not None else None
                battery_pct = int(raw_bp) if raw_bp is not None else None

                run_id = data.get("run_id") or fsm.active_run_id
                checkpoint_seq = data.get("checkpoint_seq")
                total_checkpoints = data.get("total_checkpoints")
                raw_ms = data.get("match_score")
                match_score = float(raw_ms) if raw_ms is not None else None
                latency_ms = _compute_latency_ms(data.get("timestamp"))

                if (
                    battery_v is not None
                    and battery_v < settings.BATTERY_LOW_VOLTAGE
                    and notifier.should_notify("BATTERY_LOW")
                ):
                    batt_event = SecurityEvent(
                        run_id=run_id,
                        type="BATTERY_LOW",
                        payload_json={
                            "battery_v": battery_v,
                            "battery_pct": battery_pct,
                        },
                    )
                    db.add(batt_event)
                    db.commit()
                    await manager.broadcast_to_web(
                        {
                            "type": "alert",
                            "event_type": "BATTERY_LOW",
                            "battery_v": battery_v,
                            "battery_pct": battery_pct,
                            "message": (
                                f"Điện áp pin nguy hiểm: {battery_v:.2f}V"
                                + (f" ({battery_pct}%)" if battery_pct is not None else "")
                            ),
                            "timestamp": utc_now().isoformat(),
                        }
                    )

                # [PENDING_INTEGRATION: TUANANH_MATCH_SCORE]
                # Hiện tại: Cảnh báo và chuyển ERROR_LOST nếu match_score < 0.35 liên tiếp 3 lần khi PATROLLING.
                # Cần khớp: Tuấn Anh chốt ngưỡng điểm match keyframe và điều kiện xác định lạc tuyến.
                # Hành động: Tinh chỉnh logic ở fsm.evaluate_match_score() hoặc config.py sau khi thử nghiệm CV.
                lost_triggered = fsm.update_from_telemetry(
                    state=data.get("state"),
                    checkpoint_seq=checkpoint_seq,
                    total_checkpoints=total_checkpoints,
                    match_score=match_score,
                    battery_v=battery_v,
                    battery_pct=battery_pct,
                    run_id=run_id,
                )

                if lost_triggered:
                    logger.warning("Cảnh báo: JetBot mất định vị (match_score=%s)", match_score)
                    lost_event = SecurityEvent(
                        run_id=run_id,
                        type="ERROR_LOST",
                        payload_json={
                            "checkpoint_seq": checkpoint_seq,
                            "match_score": match_score,
                            "consecutive_low_match_count": fsm.consecutive_low_match_count,
                        },
                    )
                    db.add(lost_event)
                    if run_id:
                        run_obj = db.get(PatrolRun, run_id)
                        if run_obj is not None and run_obj.result == "IN_PROGRESS":
                            run_obj.result = "LOST"
                            run_obj.ended_at = utc_now()
                            run_obj.note = "Mất định vị tuyến (match_score thấp liên tiếp)"
                    db.commit()
                    await manager.broadcast_to_web(
                        {
                            "type": "alert",
                            "event_type": "ERROR_LOST",
                            "run_id": run_id,
                            "checkpoint_seq": checkpoint_seq,
                            "match_score": match_score,
                            "message": "Cảnh báo: JetBot bị lạc tuyến (ERROR_LOST)!",
                            "timestamp": utc_now().isoformat(),
                        }
                    )

                if run_id:
                    run_obj = db.get(PatrolRun, run_id)
                    if run_obj is not None:
                        db.add(
                            RunTelemetry(
                                run_id=run_id,
                                state=fsm.state.value,
                                checkpoint_seq=checkpoint_seq,
                                match_score=match_score,
                                battery_v=battery_v,
                                battery_pct=battery_pct,
                                latency_ms=latency_ms,
                            )
                        )
                        db.commit()

                out_telemetry = dict(data)
                out_telemetry["type"] = "telemetry"
                out_telemetry["state"] = fsm.state.value
                out_telemetry["run_id"] = run_id
                if latency_ms is not None:
                    out_telemetry["latency_ms"] = latency_ms
                await manager.broadcast_to_web(out_telemetry)

            elif msg_type == "event":
                # [PENDING_INTEGRATION: TUANANH_EVENT_PAYLOAD]
                # Hiện tại: Lưu DB, giải mã `image_base64` (nếu có) ra đĩa và broadcast lên Web qua bộ đệm chống spam.
                # Cần khớp: Định dạng event_type, confidence, details và cơ chế gửi ảnh từ module YOLO/CV của Tuấn Anh.
                # Hành động: Bổ sung mapping trường nếu payload CV thực tế dùng tên khóa khác.
                event_type = str(data.get("event_type", "UNKNOWN")).strip().upper()
                run_id = data.get("run_id") or fsm.active_run_id

                if event_type == "OBSTACLE_BLOCKED":
                    fsm.state = RobotState.BLOCKED
                elif event_type == "OBSTACLE_CLEARED" and fsm.state == RobotState.BLOCKED:
                    fsm.state = RobotState.PATROLLING
                fsm.touch_heartbeat()

                if not notifier.should_notify(event_type):
                    continue

                evidence_path: Optional[str] = None
                image_b64 = data.get("image_base64")
                if image_b64:
                    try:
                        evidence_path = save_evidence_base64(
                            image_b64,
                            storage_dir=settings.STORAGE_DIR,
                            prefix=event_type.lower(),
                        )
                    except ValueError as exc:
                        logger.warning("Không giải mã được image_base64 từ event %s: %s", event_type, exc)

                event_rec = SecurityEvent(
                    run_id=run_id,
                    type=event_type,
                    confidence=data.get("confidence"),
                    evidence_path=evidence_path,
                    payload_json=data.get("details", {}),
                )
                db.add(event_rec)

                if run_id:
                    run_obj = db.get(PatrolRun, run_id)
                    if run_obj is not None:
                        if "PERSON" in event_type:
                            run_obj.person_count += 1
                        elif event_type == "OBSTACLE_BLOCKED":
                            run_obj.obstacle_count += 1

                db.commit()
                db.refresh(event_rec)

                event_out = dict(data)
                event_out.pop("image_base64", None)
                event_out["id"] = event_rec.id
                event_out["event_type"] = event_type
                event_out["run_id"] = run_id
                event_out["evidence_path"] = evidence_path
                event_out["evidence_url"] = f"/storage/{evidence_path}" if evidence_path else None
                event_out["timestamp"] = event_rec.timestamp.isoformat()
                await manager.broadcast_to_web({"type": "event", "data": event_out})

            elif msg_type == "heartbeat":
                fsm.touch_heartbeat()
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "heartbeat_ack",
                            "timestamp": utc_now().isoformat(),
                        }
                    )
                )

            elif msg_type == "status":
                parsed_state = parse_robot_state(data.get("state"))
                if parsed_state is not None:
                    fsm.state = parsed_state
                fsm.touch_heartbeat()

                patrol_status = str(
                    data.get("patrol_status") or data.get("result") or ""
                ).strip().upper()
                run_id = data.get("run_id") or fsm.active_run_id
                if patrol_status in {"COMPLETED", "ABORTED", "LOST"} and run_id:
                    run_obj = db.get(PatrolRun, run_id)
                    if run_obj is not None and run_obj.result == "IN_PROGRESS":
                        run_obj.result = patrol_status
                        run_obj.ended_at = utc_now()
                        if data.get("note"):
                            run_obj.note = str(data["note"])
                        db.commit()
                    if fsm.active_run_id == run_id:
                        fsm.active_run_id = None

                await manager.broadcast_to_web(data)

            elif msg_type == "frame":
                fsm.touch_heartbeat()
                manager.latest_frame_b64 = data.get("image_base64") or data.get("frame")
                await manager.broadcast_to_web(data)

            else:
                fsm.touch_heartbeat()
                await manager.broadcast_to_web(data)

    except WebSocketDisconnect:
        manager.disconnect_robot()
        active_run_id = fsm.active_run_id
        fsm.on_robot_disconnected()
        if active_run_id:
            run_obj = db.get(PatrolRun, active_run_id)
            if run_obj is not None and run_obj.result == "IN_PROGRESS":
                run_obj.result = "ABORTED"
                run_obj.ended_at = utc_now()
                run_obj.note = "Robot disconnected during patrol"
                db.commit()
            fsm.active_run_id = None

        await manager.broadcast_to_web(
            {
                "type": "system",
                "state": "OFFLINE",
                "robot_connected": False,
                "message": "Mất kết nối với JetBot!",
                "timestamp": utc_now().isoformat(),
            }
        )


@ws_router.websocket("/ws/web")
async def websocket_web_endpoint(
    websocket: WebSocket,
    db: Session = Depends(get_db),
) -> None:
    """WebSocket channel for Web Dashboard clients to receive live updates and send control commands."""
    await manager.connect_web(websocket)
    await websocket.send_text(
        json.dumps({"type": "snapshot", "data": fsm.get_snapshot()})
    )

    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"type": "error", "message": "Payload JSON không hợp lệ"})
                )
                continue

            if not isinstance(data, dict) or not data.get("cmd"):
                await websocket.send_text(
                    json.dumps({"type": "error", "message": "Thiếu trường 'cmd'"})
                )
                continue

            # [PENDING_INTEGRATION: FRONTEND_WS_TOPICS]
            # Hiện tại: Tiếp nhận lệnh theo chuẩn cmd (move, stop, emergency_stop, start_teach, end_teach, start_patrol, pause_patrol, resume_patrol).
            # Cần khớp: Tên lệnh và cấu trúc payload từ giao diện Web của Frontend.
            # Hành động: Cập nhật bảng alias trong schemas/ws_schema.py nếu Frontend gửi tên lệnh khác.
            cmd = normalize_web_command(str(data["cmd"]))

            if cmd == "emergency_stop":
                await manager.send_emergency_stop()
                fsm.apply_command_transition("emergency_stop")
                estop_event = SecurityEvent(
                    run_id=fsm.active_run_id,
                    type="EMERGENCY_STOP",
                    payload_json={"source": "web"},
                )
                db.add(estop_event)
                db.commit()
                await manager.broadcast_to_web(
                    {
                        "type": "system",
                        "event_type": "EMERGENCY_STOP",
                        "state": fsm.state.value,
                        "message": "Đã kích hoạt DỪNG KHẨN CẤP!",
                        "timestamp": utc_now().isoformat(),
                    }
                )
                continue

            valid, reason = fsm.validate_command(cmd)
            if not valid:
                await websocket.send_text(
                    json.dumps({"type": "error", "cmd": cmd, "reason": reason})
                )
                continue

            if cmd == "move":
                left = float(data.get("left", 0.0))
                right = float(data.get("right", 0.0))
                hold = bool(data.get("hold", False))
                await manager.forward_teleop_cmd(left, right, hold=hold)
                fsm.apply_command_transition("move")
            elif cmd == "stop":
                await manager.stop_teleop()
                await manager.send_to_robot(
                    {"cmd": "stop", "timestamp": utc_now().isoformat()}
                )
                fsm.apply_command_transition("stop")
            else:
                forward_payload = dict(data)
                forward_payload["cmd"] = cmd
                forward_payload.setdefault("timestamp", utc_now().isoformat())
                await manager.send_to_robot(forward_payload)
                fsm.apply_command_transition(
                    cmd,
                    route_id=data.get("route_id"),
                    run_id=data.get("run_id"),
                )

    except WebSocketDisconnect:
        manager.disconnect_web(websocket)
