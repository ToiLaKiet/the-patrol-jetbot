"""Tests for live robot status endpoint, run telemetry retrieval, and CSV export."""

from fastapi.testclient import TestClient


def test_robot_status_and_telemetry_csv_export(client: TestClient) -> None:
    status_resp = client.get("/api/v1/telemetry/robot/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["state"] == "OFFLINE"

    route_id = client.post("/api/v1/routes/", json={"name": "Tuyến Telemetry"}).json()["id"]
    run_id = client.post("/api/v1/patrols/start", json={"route_id": route_id}).json()["id"]

    with client.websocket_connect("/ws/robot") as robot_ws:
        robot_ws.send_json(
            {
                "type": "telemetry",
                "run_id": run_id,
                "state": "PATROLLING",
                "checkpoint_seq": 3,
                "match_score": 0.89,
                "battery_v": 11.8,
                "battery_pct": 73,
            }
        )
        # Ensure robot status reflects telemetry before disconnect
        mid_status = client.get("/api/v1/telemetry/robot/status").json()
        assert mid_status["robot_connected"] is True
        assert mid_status["checkpoint_seq"] == 3

    telem_resp = client.get(f"/api/v1/telemetry/{run_id}")
    assert telem_resp.status_code == 200
    rows = telem_resp.json()
    assert len(rows) == 1
    assert rows[0]["match_score"] == 0.89

    csv_resp = client.get(f"/api/v1/telemetry/{run_id}/export.csv")
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    lines = csv_resp.text.strip().splitlines()
    assert lines[0] == "id,run_id,timestamp,state,checkpoint_seq,match_score,battery_v,battery_pct,latency_ms"
    assert len(lines) == 2
    assert run_id in lines[1]
