from fastapi import APIRouter
from nexus_app.api.v1.auth import router as auth_router
from nexus_app.api.v1.projects import router as projects_router
from nexus_app.api.v1.inspect import router as inspect_router
from nexus_app.api.v1.ai import router as ai_router
from nexus_app.api.v1.jobs import router as jobs_router
from nexus_app.api.v1.datasets import router as datasets_router
from nexus_app.api.v1.radar import router as radar_router
from nexus_app.api.v1.schedules import router as schedules_router
from nexus_app.api.v1.rag import router as rag_router
from nexus_app.api.v1.health import router as health_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(projects_router)
api_v1_router.include_router(inspect_router)
api_v1_router.include_router(ai_router)
api_v1_router.include_router(jobs_router)
api_v1_router.include_router(datasets_router)
api_v1_router.include_router(radar_router)
api_v1_router.include_router(schedules_router)
api_v1_router.include_router(rag_router)
