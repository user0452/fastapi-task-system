from fastapi import APIRouter

from app.modules.account.router import router as account_router
from app.modules.adaptive.router import router as adaptive_router
from app.modules.auth.router import router as auth_router
from app.modules.courses.router import router as courses_router
from app.modules.materials.router import router as materials_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(account_router)
api_router.include_router(adaptive_router)
api_router.include_router(courses_router)
api_router.include_router(materials_router)
