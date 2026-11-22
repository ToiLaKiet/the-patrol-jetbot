"""End-to-end WebSocket tests covering /ws/robot <-> /ws/web relay, safety alerts, and commands."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings
from tests.conftest import VALID_JPEG_B64


def test_websocket_telemetry_alerts_events_and_disconnect(client: TestClient) -> None:
    route_id = client.post("/api/v1/routes/", json={"name": "Tuyến WS"}).json()["id"]
    run_id = client.post("/api/v1/patrols/start", json={"route_id": route_id}).json()["id"]

    with client.websocket_connect("/ws/web") as web_ws:
        snapshot = web_ws.receive_json()
        assert snapshot["type"] == "snapshot"
        assert snapshot["data"]["state"] == "OFFLINE"

        with client.websocket_connect("/ws/robot") as robot_ws:
            online_msg = web_ws.receive_json()
            assert online_msg["type"] == "system"
            assert online_msg["state"] == "IDLE"
            assert online_msg["robot_connected"] is True

            # Low battery telemetry should trigger BATTERY_LOW alert + broadcast telemetry
            robot_ws.send_json(
                {
                    "type": "telemetry",
                    "run_id": run_id,
                    "state": "PATROLLING",
                    "checkpoint_seq": 1,
                    "match_score": 0.85,
                    "battery_v": 9.9,
                    "battery_pct": 10,
                }
            )
            alert_msg = web_ws.receive_json()
            assert alert_msg["type"] == "alert"
            assert alert_msg["event_type"] == "BATTERY_LOW"
            telem_msg = web_ws.receive_json()
            assert telem_msg["type"] == "telemetry"
            assert telem_msg["checkpoint_seq"] == 1

            # Security event with base64 evidence saves file & increments run person_count
            robot_ws.send_json(
                {
                    "type": "event",
                    "run_id": run_id,
                    "event_type": "PERSON_DETECTED",
                    "confidence": 0.95,
                    "image_base64": VALID_JPEG_B64,
                    "details": {"note": "Detected in test"},
                }
            )
            event_msg = web_ws.receive_json()
            assert event_msg["type"] == "event"
            assert event_msg["data"]["event_type"] == "PERSON_DETECTED"
            ev_path = event_msg["data"]["evidence_path"]
            assert (Path(settings.STORAGE_DIR) / ev_path).is_file()

            # Web -> Robot teleop & emergency stop commands
            web_ws.send_json({"cmd": "emergency_stop"})
            fwd_estop = robot_ws.receive_json()
            assert fwd_estop["cmd"] == "emergency_stop"
            estop_sys = web_ws.receive_json()
            assert estop_sys["event_type"] == "EMERGENCY_STOP"

            web_ws.send_json({"cmd": "move", "left": 0.2, "right": 0.2})
            fwd_move = robot_ws.receive_json()
            assert fwd_move["cmd"] == "move"
            assert fwd_move["left"] == 0.2

        # Robot disconnected while run was IN_PROGRESS -> broadcasts OFFLINE & aborts run
        offline_msg = web_ws.receive_json()
        assert offline_msg["type"] == "system"
        assert offline_msg["state"] == "OFFLINE"

    run_detail = client.get(f"/api/v1/patrols/{run_id}").json()
    assert run_detail["result"] == "ABORTED"
    assert run_detail["person_count"] == 1


def test_websocket_three_low_match_scores_trigger_error_lost(client: TestClient) -> None:
    route_id = client.post("/api/v1/routes/", json={"name": "Tuyến Lost"}).json()["id"]
    run_id = client.post("/api/v1/patrols/start", json={"route_id": route_id}).json()["id"]

    with client.websocket_connect("/ws/web") as web_ws:
        _ = web_ws.receive_json()  # snapshot
        with client.websocket_connect("/ws/robot") as robot_ws:
            _ = web_ws.receive_json()  # IDLE online

            for seq in range(1, 4):
                robot_ws.send_json(
                    {
                        "type": "telemetry",
                        "run_id": run_id,
                        "state": "PATROLLING",
                        "checkpoint_seq": seq,
                        "match_score": 0.20,
                        "battery_v": 11.9,
                        "battery_pct": 77,
                    }
                )
                if seq < 3:
                    t_msg = web_ws.receive_json()
                    assert t_msg["type"] == "telemetry"
                else:
                    lost_alert = web_ws.receive_json()
                    assert lost_alert["type"] == "alert"
                    assert lost_alert["event_type"] == "ERROR_LOST"
                    t_msg = web_ws.receive_json()
                    assert t_msg["state"] == "ERROR_LOST"

        _ = web_ws.receive_json()  # OFFLINE

    run_detail = client.get(f"/api/v1/patrols/{run_id}").json()
    assert run_detail["result"] == "LOST"
