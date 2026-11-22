"""Application configuration with integration tag markers."""

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "The Patrol JetBot Backend"
    API_V1_STR: str = "/api/v1"

    # [PENDING_INTEGRATION: FRONTEND_CORS]
    # Hiện tại: Cho phép tất cả origins ("*") để test LAN không bị chặn.
    # Cần khớp: Danh sách domain / IP cụ thể của Frontend khi deploy thực tế.
    # Hành động: Thay ["*"] bằng danh sách origin chính xác (ví dụ ["http://localhost:5173"]).
    CORS_ORIGINS: List[str] = ["*"]

    # [PENDING_INTEGRATION: KIET_ROBOT_NET]
    # Hiện tại: Mặc định chờ JetBot kết nối ngược vào WebSocket /ws/robot của Backend.
    # Cần khớp: Xác nhận JetBot mở WebSocket tới Backend hay Backend chủ động gọi cổng 8100 của JetBot.
    # Hành động: Nếu Backend chủ động gọi sang JetBot, cập nhật URI này và bật client chủ động.
    JETBOT_AGENT_BASE_URL: str = "http://jetbot.local:8100"

    # Thư mục lưu trữ nội bộ và cơ sở dữ liệu SQLite
    STORAGE_DIR: str = "storage"
    DATABASE_URL: str = "sqlite:///./patrol_bot.db"

    # Ngưỡng an toàn, cảnh báo và chu kỳ điều khiển
    BATTERY_LOW_VOLTAGE: float = 10.2
    MATCH_SCORE_THRESHOLD: float = 0.35
    MATCH_SCORE_LOST_STREAK: int = 3
    TELEOP_REPEAT_INTERVAL_MS: int = 200
    TELEOP_HOLD_TIMEOUT_S: float = 1.0
    HEARTBEAT_TIMEOUT_S: float = 10.0
    ALERT_COOLDOWN_SECONDS: float = 10.0


settings = Settings()
