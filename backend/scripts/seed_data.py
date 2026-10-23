import io
import time
import uuid
from datetime import datetime, timedelta, timezone

def utc_now() -> datetime:
    return datetime.now(timezone.utc)
from PIL import Image, ImageDraw
from sqlalchemy.orm import Session
from app.config import settings
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.models.route import Route, Checkpoint
from app.models.patrol import PatrolSession
from app.models.event import SecurityEvent, RobotLog
from app.models.robot import RobotState

def create_sample_keyframe(text: str) -> str:
    filename = f"seed_keyframe_{uuid.uuid4().hex[:6]}.jpg"
    filepath = settings.KEYFRAME_DIR / filename
    
    img = Image.new("RGB", (640, 480), color=(26, 32, 44))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 620, 460], outline=(66, 153, 225), width=2)
    draw.text((40, 40), "THE PATROL JETBOT - REFERENCE KEYFRAME", fill=(255, 255, 255))
    draw.text((40, 70), text, fill=(160, 174, 192))
    
    # Draw simple hallway perspective
    draw.line([320, 240, 40, 440], fill=(45, 55, 72), width=2)
    draw.line([320, 240, 600, 440], fill=(45, 55, 72), width=2)
    draw.line([40, 440, 600, 440], fill=(45, 55, 72), width=2)
    
    img.save(filepath, format="JPEG", quality=85)
    return filename

def create_sample_snapshot() -> str:
    filename = f"seed_snapshot_person_{uuid.uuid4().hex[:6]}.jpg"
    filepath = settings.UPLOAD_DIR / filename
    
    img = Image.new("RGB", (640, 480), color=(18, 22, 30))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 620, 460], outline=(239, 68, 68), width=2)
    draw.text((40, 40), "SECURITY ALERT: PERSON DETECTED", fill=(239, 68, 68))
    
    # Draw simulated person bounding box
    px, py, pw, ph = 260, 160, 110, 240
    draw.rectangle([px, py, px + pw, py + ph], outline=(239, 68, 68), width=3)
    draw.text((px, py - 20), "PERSON 94.8%", fill=(239, 68, 68))
    draw.ellipse([px + 35, py + 15, px + 75, py + 65], fill=(185, 28, 28))
    draw.rectangle([px + 25, py + 65, px + 85, py + 180], fill=(153, 27, 27))
    
    img.save(filepath, format="JPEG", quality=85)
    return filename

def seed_database():
    print("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()

    try:
        # Check if route already exists
        existing_route = db.query(Route).filter(Route.name == "Tuyến Tuần Tra Tầng 1 - Khu Văn Phòng").first()
        if existing_route:
            print("Database already contains seed route. Skipping.")
            return

        print("Seeding sample Patrol Route with Checkpoints...")
        route = Route(
            name="Tuyến Tuần Tra Tầng 1 - Khu Văn Phòng",
            description="Tuyến tuần tra chuẩn qua hành lang khu văn phòng, sảnh chờ và cửa ra vào số 2.",
            status="SAVED",
            checkpoint_count=6,
            total_distance=18.5,
            duration=45.0,
            is_active=True
        )
        db.add(route)
        db.commit()
        db.refresh(route)

        waypoints = [
            {"idx": 0, "offset": 0.0, "x": 0.0, "y": 0.0, "theta": 0.0, "desc": "Điểm xuất phát - Trạm sạc"},
            {"idx": 1, "offset": 8.0, "x": 3.0, "y": 0.0, "theta": 0.0, "desc": "Hành lang A1 - Trước phòng IT"},
            {"idx": 2, "offset": 16.0, "x": 6.5, "y": 0.0, "theta": 1.57, "desc": "Khúc cua góc vuông số 1 (Rẽ trái 90 độ)"},
            {"idx": 3, "offset": 25.0, "x": 6.5, "y": 5.0, "theta": 1.57, "desc": "Hành lang B2 - Sảnh chờ trung tâm"},
            {"idx": 4, "offset": 35.0, "x": 3.0, "y": 5.0, "theta": 3.14, "desc": "Cửa kiểm soát an ninh số 2"},
            {"idx": 5, "offset": 45.0, "x": 0.0, "y": 0.0, "theta": 0.0, "desc": "Về điểm ban đầu hoàn tất vòng lặp"}
        ]

        for wp in waypoints:
            kf_name = create_sample_keyframe(f"Checkpoint {wp['idx']}: {wp['desc']}")
            cp = Checkpoint(
                route_id=route.id,
                sequence_idx=wp["idx"],
                timestamp_offset=wp["offset"],
                x=wp["x"],
                y=wp["y"],
                theta=wp["theta"],
                linear_speed=0.4,
                angular_speed=0.0 if wp["idx"] not in [2, 4] else 0.5,
                keyframe_filename=kf_name,
                metadata_json=f'{{"description": "{wp["desc"]}"}}'
            )
            db.add(cp)

        # Seed Patrol Session
        print("Seeding past Patrol Session...")
        session = PatrolSession(
            route_id=route.id,
            status="COMPLETED",
            started_at=utc_now() - timedelta(minutes=25),
            ended_at=utc_now() - timedelta(minutes=15),
            current_checkpoint_idx=5,
            total_checkpoints=6,
            progress_percent=100.0,
            obstacle_encounters=1,
            person_detections=1,
            notes="Hoàn thành tuần tra vòng 1. Phát hiện 1 người tại sảnh B2 và 1 vật cản được xử lý tự động."
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        # Seed Security Event
        print("Seeding Security Events...")
        snapshot_name = create_sample_snapshot()
        sec_event = SecurityEvent(
            session_id=session.id,
            route_id=route.id,
            event_type="PERSON_DETECTED",
            severity="CRITICAL",
            confidence=0.948,
            bounding_box="[160, 260, 400, 370]",
            snapshot_filename=snapshot_name,
            description="Phát hiện người lạ tại hành lang B2 lúc 23:45",
            timestamp=utc_now() - timedelta(minutes=20),
            resolved=False
        )
        db.add(sec_event)

        obs_event = SecurityEvent(
            session_id=session.id,
            route_id=route.id,
            event_type="OBSTACLE_BLOCKED",
            severity="WARNING",
            confidence=0.91,
            description="Thùng hàng cản đường (0.35m) tại checkpoint 3. Robot dừng 4s rồi tiếp tục.",
            timestamp=utc_now() - timedelta(minutes=18),
            resolved=True
        )
        db.add(obs_event)

        # Seed Robot Logs
        log1 = RobotLog(
            timestamp=utc_now() - timedelta(minutes=25),
            level="INFO",
            source="BACKEND",
            message="Khởi động phiên tuần tra tự động (Teach & Repeat)"
        )
        log2 = RobotLog(
            timestamp=utc_now() - timedelta(minutes=20),
            level="WARNING",
            source="VISION",
            message="Computer Vision Module: Phát hiện người với độ tin cậy 94.8%"
        )
        db.add(log1)
        db.add(log2)

        # Seed Robot State
        robot_state = db.query(RobotState).filter(RobotState.robot_id == "jetbot_01").first()
        if not robot_state:
            robot_state = RobotState(
                robot_id="jetbot_01",
                connection_status="CONNECTED",
                current_mode="IDLE",
                battery_percentage=98.0,
                battery_voltage=12.4,
                wifi_rssi=-48,
                last_heartbeat=utc_now()
            )
            db.add(robot_state)

        db.commit()
        print("Seed data created successfully!")

    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
