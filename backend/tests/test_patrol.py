def test_patrol_lifecycle(client):
    # Setup route with checkpoints
    route_res = client.post("/api/v1/routes", json={"name": "Patrol Test Route"})
    route_id = route_res.json()["id"]

    for i in range(3):
        client.post(f"/api/v1/routes/{route_id}/checkpoints", json={
            "sequence_idx": i,
            "x": float(i),
            "y": 0.0
        })

    # Start patrol
    start_res = client.post("/api/v1/patrol/start", json={
        "route_id": route_id,
        "notes": "Testing repeat patrol"
    })
    assert start_res.status_code == 200
    session = start_res.json()
    assert session["status"] == "RUNNING"
    session_id = session["id"]

    # Active patrol query
    active_res = client.get("/api/v1/patrol/active")
    assert active_res.status_code == 200
    assert active_res.json()["id"] == session_id

    # Update progress
    prog_res = client.post(f"/api/v1/patrol/{session_id}/progress", json={
        "current_checkpoint_idx": 1,
        "progress_percent": 33.3,
        "status": "RUNNING"
    })
    assert prog_res.status_code == 200
    assert prog_res.json()["current_checkpoint_idx"] == 1

    # Pause patrol
    pause_res = client.post(f"/api/v1/patrol/{session_id}/pause")
    assert pause_res.status_code == 200
    assert pause_res.json()["status"] == "PAUSED"

    # Resume patrol
    resume_res = client.post(f"/api/v1/patrol/{session_id}/resume")
    assert resume_res.status_code == 200
    assert resume_res.json()["status"] == "RUNNING"

    # Finish patrol
    complete_res = client.post(f"/api/v1/patrol/{session_id}/progress", json={
        "current_checkpoint_idx": 2,
        "progress_percent": 100.0,
        "status": "COMPLETED"
    })
    assert complete_res.status_code == 200
    assert complete_res.json()["status"] == "COMPLETED"
