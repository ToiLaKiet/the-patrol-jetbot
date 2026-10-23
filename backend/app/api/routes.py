from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.config import settings
from app.db.session import get_db
from app.schemas.route import (
    RouteCreate, RouteUpdate, RouteResponse, RouteStartRecording, RouteExport,
    CheckpointCreate, CheckpointResponse
)
from app.services.route_service import route_service

router = APIRouter(prefix="/routes", tags=["Route Management"])

def _build_checkpoint_response(cp) -> CheckpointResponse:
    keyframe_url = f"/api/v1/routes/{cp.route_id}/keyframes/{cp.keyframe_filename}" if cp.keyframe_filename else None
    return CheckpointResponse(
        id=cp.id,
        route_id=cp.route_id,
        sequence_idx=cp.sequence_idx,
        timestamp_offset=cp.timestamp_offset,
        x=cp.x,
        y=cp.y,
        theta=cp.theta,
        linear_speed=cp.linear_speed,
        angular_speed=cp.angular_speed,
        keyframe_url=keyframe_url,
        visual_features=cp.visual_features,
        metadata_json=cp.metadata_json
    )

def _build_route_response(route) -> RouteResponse:
    checkpoints = [_build_checkpoint_response(cp) for cp in route.checkpoints] if route.checkpoints else []
    return RouteResponse(
        id=route.id,
        name=route.name,
        description=route.description,
        status=route.status,
        total_distance=round(route.total_distance, 2),
        duration=round(route.duration, 2),
        checkpoint_count=route.checkpoint_count,
        is_active=route.is_active,
        created_at=route.created_at,
        updated_at=route.updated_at,
        checkpoints=checkpoints
    )

@router.get("", response_model=List[RouteResponse], summary="List all saved routes")
def list_routes(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    routes = route_service.list_routes(db, skip=skip, limit=limit)
    return [_build_route_response(r) for r in routes]

@router.post("", response_model=RouteResponse, summary="Create new route entry")
def create_route(data: RouteCreate, db: Session = Depends(get_db)):
    route = route_service.create_route(db, data)
    return _build_route_response(route)

@router.post("/start-recording", response_model=RouteResponse, summary="Start route recording in TEACH mode")
async def start_recording(data: RouteStartRecording, db: Session = Depends(get_db)):
    route = await route_service.start_recording(db, data)
    return _build_route_response(route)

@router.post("/{route_id}/stop-recording", response_model=RouteResponse, summary="Stop route recording")
async def stop_recording(route_id: str, db: Session = Depends(get_db)):
    try:
        route = await route_service.stop_recording(db, route_id)
        return _build_route_response(route)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{route_id}", response_model=RouteResponse, summary="Get route details with checkpoints")
def get_route(route_id: str, db: Session = Depends(get_db)):
    route = route_service.get_route(db, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return _build_route_response(route)

@router.put("/{route_id}", response_model=RouteResponse, summary="Update route details")
def update_route(route_id: str, data: RouteUpdate, db: Session = Depends(get_db)):
    route = route_service.update_route(db, route_id, data)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return _build_route_response(route)

@router.delete("/{route_id}", summary="Delete route and its keyframes")
def delete_route(route_id: str, db: Session = Depends(get_db)):
    success = route_service.delete_route(db, route_id)
    if not success:
        raise HTTPException(status_code=404, detail="Route not found")
    return {"success": True, "message": f"Route {route_id} deleted"}

@router.post("/{route_id}/checkpoints", response_model=CheckpointResponse, summary="Add a checkpoint to a route")
async def add_checkpoint(route_id: str, data: CheckpointCreate, db: Session = Depends(get_db)):
    try:
        cp = await route_service.add_checkpoint(db, route_id, data)
        return _build_checkpoint_response(cp)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{route_id}/keyframes/{filename}", summary="Download keyframe image")
def get_keyframe(route_id: str, filename: str):
    file_path = settings.KEYFRAME_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Keyframe image not found")
    return FileResponse(file_path, media_type="image/jpeg")

@router.get("/{route_id}/export", response_model=RouteExport, summary="Export route data as JSON")
def export_route(route_id: str, db: Session = Depends(get_db)):
    route = route_service.get_route(db, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return _build_route_response(route)
