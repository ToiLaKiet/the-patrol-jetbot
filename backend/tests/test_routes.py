def test_create_and_get_route(client):
    res = client.post("/api/v1/routes", json={
        "name": "Route Test 1",
        "description": "Description for test route"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Route Test 1"
    assert data["status"] == "SAVED"
    route_id = data["id"]

    # Get route details
    get_res = client.get(f"/api/v1/routes/{route_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == route_id

def test_route_recording_lifecycle(client):
    # Start recording
    start_res = client.post("/api/v1/routes/start-recording", json={
        "name": "Live Teach Route",
        "description": "Recorded live via Teach Mode"
    })
    assert start_res.status_code == 200
    route = start_res.json()
    assert route["status"] == "RECORDING"
    route_id = route["id"]

    # Add checkpoints
    cp1_res = client.post(f"/api/v1/routes/{route_id}/checkpoints", json={
        "sequence_idx": 0,
        "timestamp_offset": 0.0,
        "x": 0.0,
        "y": 0.0,
        "theta": 0.0,
        "linear_speed": 0.4,
        "angular_speed": 0.0
    })
    assert cp1_res.status_code == 200

    cp2_res = client.post(f"/api/v1/routes/{route_id}/checkpoints", json={
        "sequence_idx": 1,
        "timestamp_offset": 5.0,
        "x": 2.0,
        "y": 0.0,
        "theta": 0.0,
        "linear_speed": 0.4,
        "angular_speed": 0.0
    })
    assert cp2_res.status_code == 200

    # Stop recording
    stop_res = client.post(f"/api/v1/routes/{route_id}/stop-recording")
    assert stop_res.status_code == 200
    final_route = stop_res.json()
    assert final_route["status"] == "SAVED"
    assert final_route["checkpoint_count"] == 2
    assert final_route["total_distance"] == 2.0

def test_delete_route(client):
    res = client.post("/api/v1/routes", json={"name": "To Delete"})
    route_id = res.json()["id"]

    del_res = client.delete(f"/api/v1/routes/{route_id}")
    assert del_res.status_code == 200

    get_res = client.get(f"/api/v1/routes/{route_id}")
    assert get_res.status_code == 404
