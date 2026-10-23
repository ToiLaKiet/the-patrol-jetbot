from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.route import Route
from app.schemas.patrol import PatrolStartRequest, PatrolProgressUpdate, PatrolSessionResponse
from app.services.patrol_service import patrol_service

router = APIRouter(prefix="/patrol", tags=["Patrol Management"])

def _build_session_response(session, db: Session) -> PatrolSessionResponse:
    route = db.query(Route).filter(Route.id == session.route_id).first()
    return PatrolSessionResponse(
        id=session.id,
        route_id=session.route_id,
        route_name=route.name if route else None,
        status=session.status,
        started_at=session.started_at,
        ended_at=session.ended_at,
        current_checkpoint_idx=session.current_checkpoint_idx,
        total_checkpoints=session.total_checkpoints,
        progress_percent=round(session.progress_percent, 1),
        obstacle_encounters=session.obstacle_encounters,
        person_detections=session.person_detections,
        notes=session.notes
    )

@router.post("/start", response_model=PatrolSessionResponse, summary="Start autonomous patrol on a route")
async def start_patrol(data: PatrolStartRequest, db: Session = Depends(get_db)):
    try:
        session = await patrol_service.start_patrol(db, data)
        return _build_session_response(session, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/active", response_model=Optional[PatrolSessionResponse], summary="Get current active patrol session")
def get_active_patrol(db: Session = Depends(get_db)):
    session = patrol_service.get_active_session(db)
    if not session:
        return None
    return _build_session_response(session, db)

@router.get("/sessions", response_model=List[PatrolSessionResponse], summary="List past patrol sessions")
def list_sessions(
    route_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    sessions = patrol_service.list_sessions(db, route_id=route_id, skip=skip, limit=limit)
    return [_build_session_response(s, db) for s in sessions]

@router.get("/sessions/{session_id}", response_model=PatrolSessionResponse, summary="Get patrol session details")
def get_session(session_id: str, db: Session = Depends(get_db)):
    session = patrol_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Patrol session not found")
    return _build_session_response(session, db)

@router.post("/{session_id}/progress", response_model=PatrolSessionResponse, summary="Update patrol progress")
async def update_progress(session_id: str, data: PatrolProgressUpdate, db: Session = Depends(get_db)):
    session = await patrol_service.update_progress(db, session_id, data)
    if not session:
        raise HTTPException(status_code=404, detail="Patrol session not found")
    return _build_session_response(session, db)

@router.post("/{session_id}/pause", response_model=PatrolSessionResponse, summary="Pause patrol")
async def pause_patrol(session_id: str, db: Session = Depends(get_db)):
    session = await patrol_service.pause_patrol(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Patrol session not found")
    return _build_session_response(session, db)

@router.post("/{session_id}/resume", response_model=PatrolSessionResponse, summary="Resume paused patrol")
async def resume_patrol(session_id: str, db: Session = Depends(get_db)):
    session = await patrol_service.resume_patrol(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Patrol session not found")
    return _build_session_response(session, db)

@router.post("/{session_id}/stop", response_model=PatrolSessionResponse, summary="Stop/abort patrol")
async def stop_patrol(session_id: str, reason: str = Query("Operator stopped patrol"), db: Session = Depends(get_db)):
    session = await patrol_service.stop_patrol(db, session_id, reason)
    if not session:
        raise HTTPException(status_code=404, detail="Patrol session not found")
    return _build_session_response(session, db)
