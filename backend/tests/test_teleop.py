def test_teleop_commands(client):
    # Forward
    fwd_res = client.post("/api/v1/teleop/command", json={
        "command": "FORWARD",
        "linear_speed": 0.5
    })
    assert fwd_res.status_code == 200
    assert fwd_res.json()["applied_linear"] == 0.5

    # Stop
    stop_res = client.post("/api/v1/teleop/command", json={
        "command": "STOP"
    })
    assert stop_res.status_code == 200
    assert stop_res.json()["applied_linear"] == 0.0

def test_emergency_stop(client):
    res = client.post("/api/v1/teleop/emergency-stop", json={
        "reason": "Test E-stop"
    })
    assert res.status_code == 200
    assert res.json()["robot_mode"] == "EMERGENCY_STOP"

    status_res = client.get("/api/v1/robot/status")
    assert status_res.json()["current_mode"] == "EMERGENCY_STOP"

def test_robot_telemetry_and_heartbeat(client):
    hb_res = client.post("/api/v1/robot/heartbeat")
    assert hb_res.status_code == 200
    assert hb_res.json()["status"] == "ok"

    telem_res = client.post("/api/v1/robot/telemetry", json={
        "robot_id": "jetbot_01",
        "battery_percentage": 88.5,
        "wifi_rssi": -45,
        "current_x": 1.25,
        "current_y": 2.50
    })
    assert telem_res.status_code == 200
    assert telem_res.json()["battery_percentage"] == 88.5
