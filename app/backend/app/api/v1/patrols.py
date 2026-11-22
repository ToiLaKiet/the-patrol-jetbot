"""REST API endpoints for managing patrol runs and computing acceptance-criteria KPIs."""

from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.fsm import RobotState, fsm
from app.db.base import utc_now
from app.db.session import get_db
from app.models.event import SecurityEvent
from app.models.patrol import PatrolRun
from app.models.route import Route
from app.schemas.patrol_schema import (
    PatrolFinishRequest,
    PatrolKPISummaryResponse,
    PatrolRunResponse,
    PatrolStartRequest,
    RouteKPIItem,
)
from app.ws.connection_manager import manager

patrols_router = APIRouter(prefix="/patrols", tags=["Patrols"])


@patrols_router.get("/", response_model=List[PatrolRunResponse])
def list_patrol_runs(
    route_id: Optional[str] = Query(default=None),
    result: Optional[str] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List patrol runs with optional route_id/result filters and pagination."""
    query = db.query(PatrolRun)
    if route_id:
        query = query.filter(PatrolRun.route_id == route_id)
    if result:
        query = query.filter(PatrolRun.result == result.strip().upper())
    return (
        query.order_by(PatrolRun.started_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@patrols_router.post("/start", response_model=PatrolRunResponse, status_code=201)
async def start_patrol_run(
    payload: PatrolStartRequest,
    db: Session = Depends(get_db),
):
    """Start an autonomous patrol run for an existing route and notify JetBot if online."""
    route = db.get(Route, payload.route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tuyến đường")

    run_id = str(uuid.uuid4())
    run_rec = PatrolRun(
        id=run_id,
        route_id=route.id,
        result="IN_PROGRESS",
        note=payload.note,
    )
    db.add(run_rec)
    db.commit()
    db.refresh(run_rec)

    fsm.active_run_id = run_id
    fsm.active_route_id = route.id
    if fsm.robot_connected:
        fsm.state = RobotState.PATROLLING
        fsm.consecutive_low_match_count = 0
        await manager.send_to_robot(
            {
                "cmd": "start_patrol",
                "run_id": run_id,
                "route_id": route.id,
                "timestamp": utc_now().isoformat(),
            }
        )

    return run_rec


@patrols_router.get("/kpi/summary", response_model=PatrolKPISummaryResponse)
def get_kpi_summary(db: Session = Depends(get_db)):
    """Compute overall and per-route KPI metrics for acceptance reporting."""
    runs = db.query(PatrolRun).all()
    routes_by_id = {r.id: r for r in db.query(Route).all()}

    total_runs = len(runs)
    completed_runs = sum(1 for r in runs if r.result == "COMPLETED")
    aborted_runs = sum(1 for r in runs if r.result == "ABORTED")
    lost_runs = sum(1 for r in runs if r.result == "LOST")
    in_progress_runs = sum(1 for r in runs if r.result == "IN_PROGRESS")
    completion_rate_pct = (
        round((completed_runs / total_runs) * 100.0, 2) if total_runs > 0 else 0.0
    )

    events = db.query(SecurityEvent).all()
    total_obstacles_blocked = sum(1 for e in events if e.type == "OBSTACLE_BLOCKED")
    total_obstacles_cleared = sum(1 for e in events if e.type == "OBSTACLE_CLEARED")
    obstacle_stop_resume_rate_pct = (
        round(
            min(100.0, (total_obstacles_cleared / total_obstacles_blocked) * 100.0),
            2,
        )
        if total_obstacles_blocked > 0
        else 0.0
    )
    total_persons_detected = sum(1 for e in events if "PERSON" in e.type)

    grouped: dict[str, list[PatrolRun]] = {}
    for run in runs:
        grouped.setdefault(run.route_id, []).append(run)

    per_route: List[RouteKPIItem] = []
    for route_id, route_runs in grouped.items():
        r_total = len(route_runs)
        r_comp = sum(1 for r in route_runs if r.result == "COMPLETED")
        r_abort = sum(1 for r in route_runs if r.result == "ABORTED")
        r_lost = sum(1 for r in route_runs if r.result == "LOST")
        r_prog = sum(1 for r in route_runs if r.result == "IN_PROGRESS")
        route_name = routes_by_id[route_id].name if route_id in routes_by_id else route_id
        per_route.append(
            RouteKPIItem(
                route_id=route_id,
                route_name=route_name,
                total_runs=r_total,
                completed_runs=r_comp,
                aborted_runs=r_abort,
                lost_runs=r_lost,
                in_progress_runs=r_prog,
                completion_rate_pct=round((r_comp / r_total) * 100.0, 2)
                if r_total > 0
                else 0.0,
            )
        )

    return PatrolKPISummaryResponse(
        total_runs=total_runs,
        completed_runs=completed_runs,
        aborted_runs=aborted_runs,
        lost_runs=lost_runs,
        in_progress_runs=in_progress_runs,
        completion_rate_pct=completion_rate_pct,
        total_obstacles_blocked=total_obstacles_blocked,
        total_obstacles_cleared=total_obstacles_cleared,
        obstacle_stop_resume_rate_pct=obstacle_stop_resume_rate_pct,
        total_persons_detected=total_persons_detected,
        per_route=per_route,
    )


@patrols_router.get("/{run_id}", response_model=PatrolRunResponse)
def get_patrol_run(run_id: str, db: Session = Depends(get_db)):
    """Retrieve a single patrol run record by ID."""
    run_rec = db.get(PatrolRun, run_id)
    if run_rec is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lượt tuần tra")
    return run_rec


@patrols_router.post("/{run_id}/finish", response_model=PatrolRunResponse)
def finish_patrol_run(
    run_id: str,
    payload: PatrolFinishRequest,
    db: Session = Depends(get_db),
):
    """Finalize a patrol run with COMPLETED, ABORTED, or LOST status."""
    run_rec = db.get(PatrolRun, run_id)
    if run_rec is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lượt tuần tra")

    run_rec.result = payload.result
    run_rec.ended_at = utc_now()
    if payload.note is not None:
        run_rec.note = payload.note
    db.commit()
    db.refresh(run_rec)

    if fsm.active_run_id == run_id:
        fsm.active_run_id = None
        if fsm.robot_connected:
            fsm.state = (
                RobotState.ERROR_LOST if payload.result == "LOST" else RobotState.IDLE
            )

    return run_rec


@patrols_router.post("/{run_id}/stop", response_model=PatrolRunResponse)
async def stop_patrol_run(run_id: str, db: Session = Depends(get_db)):
    """Abort an active patrol run and issue a stop command to JetBot if connected."""
    run_rec = db.get(PatrolRun, run_id)
    if run_rec is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lượt tuần tra")

    run_rec.result = "ABORTED"
    run_rec.ended_at = utc_now()
    run_rec.note = run_rec.note or "Stopped via API"
    db.commit()
    db.refresh(run_rec)

    if fsm.active_run_id == run_id:
        fsm.active_run_id = None
        if fsm.robot_connected:
            fsm.state = RobotState.IDLE
    if fsm.robot_connected:
        await manager.send_to_robot(
            {"cmd": "stop", "run_id": run_id, "timestamp": utc_now().isoformat()}
        )

    return run_rec
