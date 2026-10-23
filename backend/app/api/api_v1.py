from fastapi import APIRouter
from app.api.teleop import router as teleop_router
from app.api.routes import router as routes_router
from app.api.patrol import router as patrol_router
from app.api.events import router as events_router
from app.api.robot import router as robot_router
from app.api.video import router as video_router

api_router = APIRouter()
api_router.include_router(teleop_router)
api_router.include_router(routes_router)
api_router.include_router(patrol_router)
api_router.include_router(events_router)
api_router.include_router(robot_router)
api_router.include_router(video_router)
