"""REST API endpoints for live robot status, run telemetry logs, and CSV export."""

import csv
import io
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.fsm import fsm
from app.db.session import get_db
from app.models.patrol import PatrolRun, RunTelemetry
from app.schemas.patrol_schema import TelemetryPointResponse

telemetry_router = APIRouter(prefix="/telemetry", tags=["Telemetry"])


@telemetry_router.get("/robot/status")
def get_robot_status():
    """Return the current live FSM snapshot of JetBot without waiting for WebSocket ticks."""
    return fsm.get_snapshot()


@telemetry_router.get("/{run_id}", response_model=List[TelemetryPointResponse])
def get_run_telemetry(
    run_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    """Retrieve time-series telemetry samples for a specific patrol run."""
    run_rec = db.get(PatrolRun, run_id)
    if run_rec is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lượt tuần tra")
    return (
        db.query(RunTelemetry)
        .filter(RunTelemetry.run_id == run_id)
        .order_by(RunTelemetry.timestamp.asc(), RunTelemetry.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@telemetry_router.get("/{run_id}/export.csv")
def export_run_telemetry_csv(run_id: str, db: Session = Depends(get_db)):
    """Export all telemetry samples for a patrol run as a downloadable CSV report."""
    run_rec = db.get(PatrolRun, run_id)
    if run_rec is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lượt tuần tra")

    rows = (
        db.query(RunTelemetry)
        .filter(RunTelemetry.run_id == run_id)
        .order_by(RunTelemetry.timestamp.asc(), RunTelemetry.id.asc())
        .all()
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "run_id",
            "timestamp",
            "state",
            "checkpoint_seq",
            "match_score",
            "battery_v",
            "battery_pct",
            "latency_ms",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.run_id,
                row.timestamp.isoformat() if row.timestamp else "",
                row.state or "",
                "" if row.checkpoint_seq is None else row.checkpoint_seq,
                "" if row.match_score is None else row.match_score,
                "" if row.battery_v is None else row.battery_v,
                "" if row.battery_pct is None else row.battery_pct,
                "" if row.latency_ms is None else row.latency_ms,
            ]
        )

    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="telemetry_{run_id}.csv"'
        },
    )
