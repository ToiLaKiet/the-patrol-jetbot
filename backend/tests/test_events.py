def test_person_detection_event(client):
    res = client.post("/api/v1/events", json={
        "event_type": "PERSON_DETECTED",
        "severity": "CRITICAL",
        "confidence": 0.948,
        "bounding_box": "[160, 260, 400, 370]",
        "description": "Person in restricted corridor"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["event_type"] == "PERSON_DETECTED"
    assert data["severity"] == "CRITICAL"
    assert data["confidence"] == 0.948
    event_id = data["id"]

    # Resolve event
    res_resolve = client.post(f"/api/v1/events/{event_id}/resolve")
    assert res_resolve.status_code == 200
    assert res_resolve.json()["resolved"] is True

def test_obstacle_blocked_and_cleared_events(client):
    # Obstacle blocked
    res_block = client.post("/api/v1/events", json={
        "event_type": "OBSTACLE_BLOCKED",
        "description": "Box on track (0.3m)"
    })
    assert res_block.status_code == 200

    # Status should reflect blocked mode
    status_res = client.get("/api/v1/robot/status")
    assert status_res.json()["current_mode"] == "BLOCKED"

    # Obstacle cleared
    res_clear = client.post("/api/v1/events", json={
        "event_type": "OBSTACLE_CLEARED",
        "description": "Box removed"
    })
    assert res_clear.status_code == 200

    # Status should no longer be blocked
    status_res2 = client.get("/api/v1/robot/status")
    assert status_res2.json()["current_mode"] != "BLOCKED"

def test_system_logs(client):
    log_res = client.post("/api/v1/events/system/logs", json={
        "level": "INFO",
        "source": "BACKEND",
        "message": "System self-test passed"
    })
    assert log_res.status_code == 200

    logs_list = client.get("/api/v1/events/system/logs")
    assert logs_list.status_code == 200
    assert len(logs_list.json()) >= 1
