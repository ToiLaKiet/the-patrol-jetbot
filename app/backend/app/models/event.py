"""ORM model for security, obstacle, and system events."""

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String

from app.db.base import Base, utc_now


class SecurityEvent(Base):
    """Recorded security or operational event with optional evidence image."""

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    run_id = Column(String(36), index=True, nullable=True)

    # [PENDING_INTEGRATION: TUANANH_EVENT_PAYLOAD]
    # Hiện tại: Lưu loại sự kiện, độ tin cậy, đường dẫn ảnh bằng chứng và JSON mở rộng.
    # Cần khớp: Chuẩn tên sự kiện (PERSON_DETECTED, OBSTACLE_BLOCKED, OBSTACLE_CLEARED, BATTERY_LOW, ERROR_LOST) và định dạng ảnh.
    # Hành động: Cập nhật danh sách enum/mapping nếu module YOLO/CV của Tuấn Anh dùng tên trường khác.
    type = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime, default=utc_now, nullable=False, index=True)
    confidence = Column(Float, nullable=True)
    evidence_path = Column(String(255), nullable=True)
    payload_json = Column(JSON, nullable=True)
