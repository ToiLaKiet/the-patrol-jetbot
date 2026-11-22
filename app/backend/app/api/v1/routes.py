"""REST API endpoints for managing Teach & Repeat routes and ZIP packages."""

from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.route import Checkpoint, Route
from app.schemas.route_schema import (
    CheckpointResponse,
    RouteCreate,
    RouteDetailResponse,
    RouteResponse,
    RouteUploadResponse,
)
from app.services.route_service import create_route_from_zip, delete_route_storage

routes_router = APIRouter(prefix="/routes", tags=["Routes"])


@routes_router.get("/", response_model=List[RouteResponse])
def get_routes(
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """List all stored patrol routes ordered newest first."""
    query = db.query(Route)
    if status:
        query = query.filter(Route.status == status.strip().upper())
    return query.order_by(Route.created_at.desc()).all()


@routes_router.post("/", response_model=RouteDetailResponse, status_code=201)
def create_route(
    payload: RouteCreate,
    db: Session = Depends(get_db),
):
    """Create a route and optional checkpoints directly from a JSON payload."""
    route_id = str(uuid.uuid4())
    total_duration = payload.total_duration_s
    if total_duration == 0.0 and payload.checkpoints:
        total_duration = max(cp.timestamp_offset for cp in payload.checkpoints)

    new_route = Route(
        id=route_id,
        name=payload.name,
        description=payload.description,
        checkpoint_count=len(payload.checkpoints),
        total_duration_s=total_duration,
        status="ACTIVE",
    )
    db.add(new_route)
    db.flush()

    for cp in payload.checkpoints:
        db.add(
            Checkpoint(
                route_id=route_id,
                seq=cp.seq,
                keyframe_path=cp.keyframe_path,
                timestamp_offset=cp.timestamp_offset,
                command_summary=cp.command_summary,
            )
        )

    db.commit()
    db.refresh(new_route)
    return new_route


# [PENDING_INTEGRATION: TUANANH_ROUTE_PACKAGE]
# Hiện tại: Tiếp nhận file zip, giải nén an toàn, phân tích `route.json` hoặc `samples.csv` và lưu tuyến + checkpoint vào DB.
# Cần khớp: Tên cấu trúc file bên trong zip (`route.json` + thư mục `keyframes/`) với Tuấn Anh & Kiệt.
# Hành động: Cập nhật route_service.parse_extracted_route() khi thống nhất cấu trúc gói hành trình thực tế.
@routes_router.post("/upload", response_model=RouteUploadResponse, status_code=201)
async def upload_route_package(
    name: str = Form(...),
    description: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a Teach & Repeat route ZIP package, unpack it, and index its checkpoints."""
    new_route = create_route_from_zip(db, name=name, upload_file=file, description=description)
    return {
        "message": "Tải lên tuyến thành công",
        "route": new_route,
    }


@routes_router.get("/{route_id}", response_model=RouteDetailResponse)
def get_route_detail(route_id: str, db: Session = Depends(get_db)):
    """Retrieve route metadata along with its ordered checkpoint sequence."""
    route = db.get(Route, route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tuyến đường")
    return route


@routes_router.get("/{route_id}/checkpoints", response_model=List[CheckpointResponse])
def get_route_checkpoints(route_id: str, db: Session = Depends(get_db)):
    """Retrieve ordered checkpoints for a specific route."""
    route = db.get(Route, route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tuyến đường")
    return (
        db.query(Checkpoint)
        .filter(Checkpoint.route_id == route_id)
        .order_by(Checkpoint.seq.asc())
        .all()
    )


@routes_router.delete("/{route_id}")
def delete_route(route_id: str, db: Session = Depends(get_db)):
    """Delete a route, its DB cascade records, and its unpacked package directory."""
    route = db.get(Route, route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tuyến đường")
    package_path = route.package_path
    db.delete(route)
    db.commit()
    delete_route_storage(package_path)
    return {"message": "Đã xóa tuyến đường", "route_id": route_id}
