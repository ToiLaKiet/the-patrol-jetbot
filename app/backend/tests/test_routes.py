"""Integration tests for Route CRUD and ZIP route package ingestion."""

import io
import json
from pathlib import Path
import zipfile

from fastapi.testclient import TestClient

from app.config import settings
from tests.conftest import VALID_JPEG_BYTES


def _build_route_json_zip() -> bytes:
    buf = io.BytesIO()
    manifest = {
        "name": "Hành lang B2",
        "total_duration_s": 4.5,
        "checkpoints": [
            {
                "seq": 0,
                "keyframe": "keyframes/000000.jpg",
                "timestamp_offset": 0.0,
                "command_summary": "left=0.000, right=0.000",
            },
            {
                "seq": 1,
                "keyframe": "keyframes/000001.jpg",
                "timestamp_offset": 2.2,
                "command_summary": "left=0.200, right=0.200",
            },
            {
                "seq": 2,
                "keyframe": "keyframes/000002.jpg",
                "timestamp_offset": 4.5,
                "command_summary": "left=0.000, right=0.000",
            },
        ],
    }
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("route.json", json.dumps(manifest))
        for i in range(3):
            zf.writestr(f"keyframes/{i:06d}.jpg", VALID_JPEG_BYTES)
    return buf.getvalue()


def _build_teach_recorder_zip() -> bytes:
    buf = io.BytesIO()
    csv_text = (
        "image,frame_read_s,command_s,left,right\n"
        "images/000000.jpg,0.01,-0.01,0.0,0.0\n"
        "images/000001.jpg,0.21,0.20,0.2,0.2\n"
        "images/000002.jpg,0.41,0.40,0.2,0.15\n"
    )
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("samples.csv", csv_text)
        for i in range(3):
            zf.writestr(f"images/{i:06d}.jpg", VALID_JPEG_BYTES)
    return buf.getvalue()


def test_route_json_crud_lifecycle(client: TestClient) -> None:
    create_resp = client.post(
        "/api/v1/routes/",
        json={
            "name": "Tuyến Sảnh Chính",
            "description": "Test CRUD",
            "checkpoints": [
                {"seq": 0, "timestamp_offset": 0.0, "command_summary": "start"},
                {"seq": 1, "timestamp_offset": 3.5, "command_summary": "forward"},
            ],
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    route_id = created["id"]
    assert created["checkpoint_count"] == 2
    assert created["total_duration_s"] == 3.5

    list_resp = client.get("/api/v1/routes/")
    assert list_resp.status_code == 200
    assert any(item["id"] == route_id for item in list_resp.json())

    detail_resp = client.get(f"/api/v1/routes/{route_id}")
    assert detail_resp.status_code == 200
    assert len(detail_resp.json()["checkpoints"]) == 2

    cps_resp = client.get(f"/api/v1/routes/{route_id}/checkpoints")
    assert cps_resp.status_code == 200
    assert [cp["seq"] for cp in cps_resp.json()] == [0, 1]

    del_resp = client.delete(f"/api/v1/routes/{route_id}")
    assert del_resp.status_code == 200
    assert client.get(f"/api/v1/routes/{route_id}").status_code == 404


def test_upload_route_zip_with_route_json_and_delete_cleanup(client: TestClient) -> None:
    zip_bytes = _build_route_json_zip()
    resp = client.post(
        "/api/v1/routes/upload",
        data={"name": "Tuyến Zip Chuẩn", "description": "Package chuẩn"},
        files={"file": ("route_pkg.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 201
    body = resp.json()
    route = body["route"]
    route_id = route["id"]
    assert route["checkpoint_count"] == 3
    assert route["total_duration_s"] == 4.5
    assert route["checkpoints"][0]["keyframe_path"] == f"routes/{route_id}/keyframes/000000.jpg"

    extracted_dir = Path(settings.STORAGE_DIR) / "routes" / route_id
    assert (extracted_dir / "keyframes" / "000000.jpg").is_file()

    del_resp = client.delete(f"/api/v1/routes/{route_id}")
    assert del_resp.status_code == 200
    assert not extracted_dir.exists()


def test_upload_route_zip_with_teach_recorder_samples_csv(client: TestClient) -> None:
    zip_bytes = _build_teach_recorder_zip()
    resp = client.post(
        "/api/v1/routes/upload",
        data={"name": "Tuyến TeachRecorder"},
        files={"file": ("teach_run.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 201
    route = resp.json()["route"]
    assert route["checkpoint_count"] == 3
    assert route["total_duration_s"] == 0.41
    assert route["checkpoints"][1]["command_summary"] == "left=0.200, right=0.200"


def test_upload_rejects_non_zip_and_zip_slip(client: TestClient) -> None:
    bad_ext = client.post(
        "/api/v1/routes/upload",
        data={"name": "Bad Ext"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert bad_ext.status_code == 400

    evil_buf = io.BytesIO()
    with zipfile.ZipFile(evil_buf, "w") as zf:
        zf.writestr("../../escaped.txt", b"malicious")
    zip_slip = client.post(
        "/api/v1/routes/upload",
        data={"name": "Zip Slip"},
        files={"file": ("evil.zip", evil_buf.getvalue(), "application/zip")},
    )
    assert zip_slip.status_code == 400
