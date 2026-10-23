import os
from pathlib import Path
from pydantic import BaseModel, Field

# Load optional .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Base directories
BACKEND_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseModel):
    PROJECT_NAME: str = "The Patrol Jetbot Backend Service"
    PROJECT_VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'data' / 'patrol_jetbot.db'}")
    
    # Storage Paths
    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", str(BACKEND_DIR / "data" / "uploads")))
    KEYFRAME_DIR: Path = Path(os.getenv("KEYFRAME_DIR", str(BACKEND_DIR / "data" / "keyframes")))
    STATIC_DIR: Path = Path(os.getenv("STATIC_DIR", str(BACKEND_DIR / "static")))
    
    # CORS
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "*")
    
    # Teleoperation & Robot Defaults
    ROBOT_HEARTBEAT_TIMEOUT: float = float(os.getenv("ROBOT_HEARTBEAT_TIMEOUT", "10.0"))
    DEFAULT_LINEAR_SPEED: float = float(os.getenv("DEFAULT_LINEAR_SPEED", "0.4"))
    DEFAULT_ANGULAR_SPEED: float = float(os.getenv("DEFAULT_ANGULAR_SPEED", "0.5"))
    
    # Patrol
    PATROL_CHECKPOINT_REACHED_RADIUS: float = float(os.getenv("PATROL_CHECKPOINT_REACHED_RADIUS", "0.15"))

settings = Settings()

# Ensure directories exist
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.KEYFRAME_DIR.mkdir(parents=True, exist_ok=True)
settings.STATIC_DIR.mkdir(parents=True, exist_ok=True)
