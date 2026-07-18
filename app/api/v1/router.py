from fastapi import APIRouter

from app.modules.account.router import router as account_router
from app.modules.agent.router import router as agent_router
from app.modules.auth.router import router as auth_router
from app.modules.courses.router import router as courses_router
from app.modules.learning.router import router as learning_router
from app.modules.materials.router import router as materials_router
from app.modules.resources.router import router as resources_router
from app.modules.roadmaps.router import router as roadmaps_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(account_router)
api_router.include_router(courses_router)
api_router.include_router(materials_router)
api_router.include_router(learning_router)
api_router.include_router(agent_router)
api_router.include_router(resources_router)
api_router.include_router(roadmaps_router)
