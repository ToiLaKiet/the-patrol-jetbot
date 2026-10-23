import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

from app.config import settings
from app.db.base import Base
from app.db.session import engine
from app.api.api_v1 import api_router
from app.ws.endpoints import router as ws_router

# Setup logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("patrol_jetbot")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables
    import app.models  # Register all models on Base.metadata
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info(f"{settings.PROJECT_NAME} v{settings.PROJECT_VERSION} started successfully.")
    yield
    # Shutdown
    logger.info("Shutting down backend service...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description=(
        "Backend Service for The Patrol Jetbot (Indoor security patrol robot utilizing "
        "Computer Vision and Teach & Repeat navigation). Developed by Minh (Backend Engineer)."
    ),
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS Middleware
origins = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()]
if not origins or "*" in origins:
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API and WebSocket routers
app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(ws_router)

# Mount static folder
app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")

@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "environment": settings.ENVIRONMENT
    }

@app.get("/", include_in_schema=False)
def serve_dashboard():
    index_file = settings.STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return RedirectResponse(url="/docs")
