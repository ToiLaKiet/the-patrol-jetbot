"""Tests for Security Events REST API, evidence persistence, and anti-spam cooldown."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings
from app.services.notifier import AlertNotifier
from tests.conftest import VALID_JPEG_B64, VALID_JPEG_BYTES


def test_create_event_with_base64_and_delete(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/events/",
        json={
            "type": "PERSON_DETECTED",
            "confidence": 0.94,
            "image_base64": f"data:image/jpeg;base64,{VALID_JPEG_B64}",
            "details": {"zone": "corridor"},
        },
    )
    assert resp.status_code == 201
    event = resp.json()
    assert event["type"] == "PERSON_DETECTED"
    assert event["evidence_path"].startswith("evidences/")
    assert event["evidence_url"] == f"/storage/{event['evidence_path']}"

    saved_file = Path(settings.STORAGE_DIR) / event["evidence_path"]
    assert saved_file.is_file()

    del_resp = client.delete(f"/api/v1/events/{event['id']}")
    assert del_resp.status_code == 200
    assert not saved_file.exists()


def test_upload_event_multipart_and_filter_pagination(client: TestClient) -> None:
    upload_resp = client.post(
        "/api/v1/events/upload",
        data={
            "type": "OBSTACLE_BLOCKED",
            "run_id": "run-123",
            "confidence": "0.88",
            "details_json": '{"distance_m": 0.45}',
        },
        files={"file": ("obstacle.jpg", VALID_JPEG_BYTES, "image/jpeg")},
    )
    assert upload_resp.status_code == 201
    assert upload_resp.json()["payload_json"] == {"distance_m": 0.45}

    client.post(
        "/api/v1/events/",
        json={"type": "PERSON_DETECTED", "run_id": "run-123", "bypass_cooldown": True},
    )
    client.post(
        "/api/v1/events/",
        json={"type": "PERSON_DETECTED", "run_id": "run-999", "bypass_cooldown": True},
    )

    filtered = client.get("/api/v1/events/", params={"event_type": "PERSON_DETECTED", "run_id": "run-123"})
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1

    paged = client.get("/api/v1/events/", params={"skip": 1, "limit": 1})
    assert paged.status_code == 200
    assert paged.json()["total"] == 3
    assert len(paged.json()["items"]) == 1


def test_alert_notifier_cooldown_and_priority_bypass() -> None:
    buf = AlertNotifier(cooldown_seconds=10.0)
    assert buf.should_notify("PERSON_DETECTED", now=100.0) is True
    assert buf.should_notify("PERSON_DETECTED", now=104.0) is False
    assert buf.should_notify("PERSON_DETECTED", now=110.5) is True

    # Critical state-clearing / safety events bypass cooldown immediately
    assert buf.should_notify("OBSTACLE_CLEARED", now=111.0) is True
    assert buf.should_notify("OBSTACLE_CLEARED", now=111.1) is True
    assert buf.should_notify("EMERGENCY_STOP", now=111.2) is True
