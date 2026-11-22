"""Integration tests for patrol lifecycle and KPI summary reporting."""

from fastapi.testclient import TestClient


def _create_sample_route(client: TestClient, name: str) -> str:
    resp = client.post("/api/v1/routes/", json={"name": name, "checkpoints": []})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_patrol_start_finish_and_stop(client: TestClient) -> None:
    assert client.post("/api/v1/patrols/start", json={"route_id": "missing"}).status_code == 404

    route_id = _create_sample_route(client, "Tuyến Lab")
    start_resp = client.post(
        "/api/v1/patrols/start",
        json={"route_id": route_id, "note": "Lượt thử 1"},
    )
    assert start_resp.status_code == 201
    run_id = start_resp.json()["id"]
    assert start_resp.json()["result"] == "IN_PROGRESS"

    finish_resp = client.post(
        f"/api/v1/patrols/{run_id}/finish",
        json={"result": "COMPLETED", "note": "Hoàn thành tốt"},
    )
    assert finish_resp.status_code == 200
    assert finish_resp.json()["result"] == "COMPLETED"
    assert finish_resp.json()["ended_at"] is not None

    start2 = client.post("/api/v1/patrols/start", json={"route_id": route_id}).json()
    stop_resp = client.post(f"/api/v1/patrols/{start2['id']}/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["result"] == "ABORTED"


def test_kpi_summary_calculations(client: TestClient) -> None:
    route_a = _create_sample_route(client, "Tuyến A")
    route_b = _create_sample_route(client, "Tuyến B")

    # 4 COMPLETED + 1 LOST = 80.0% completion rate
    for _ in range(3):
        run = client.post("/api/v1/patrols/start", json={"route_id": route_a}).json()
        client.post(f"/api/v1/patrols/{run['id']}/finish", json={"result": "COMPLETED"})

    run_a_lost = client.post("/api/v1/patrols/start", json={"route_id": route_a}).json()
    client.post(f"/api/v1/patrols/{run_a_lost['id']}/finish", json={"result": "LOST"})

    run_b = client.post("/api/v1/patrols/start", json={"route_id": route_b}).json()
    client.post(f"/api/v1/patrols/{run_b['id']}/finish", json={"result": "COMPLETED"})

    # Obstacle stop & resume + person detections
    for _ in range(2):
        client.post(
            "/api/v1/events/",
            json={"run_id": run_b["id"], "type": "OBSTACLE_BLOCKED", "bypass_cooldown": True},
        )
        client.post(
            "/api/v1/events/",
            json={"run_id": run_b["id"], "type": "OBSTACLE_CLEARED", "bypass_cooldown": True},
        )
    for _ in range(3):
        client.post(
            "/api/v1/events/",
            json={"run_id": run_b["id"], "type": "PERSON_DETECTED", "bypass_cooldown": True},
        )

    kpi_resp = client.get("/api/v1/patrols/kpi/summary")
    assert kpi_resp.status_code == 200
    kpi = kpi_resp.json()
    assert kpi["total_runs"] == 5
    assert kpi["completed_runs"] == 4
    assert kpi["lost_runs"] == 1
    assert kpi["completion_rate_pct"] == 80.0
    assert kpi["total_obstacles_blocked"] == 2
    assert kpi["total_obstacles_cleared"] == 2
    assert kpi["obstacle_stop_resume_rate_pct"] == 100.0
    assert kpi["total_persons_detected"] == 3
    assert len(kpi["per_route"]) == 2
