from fastapi import APIRouter
from app.api.v1.endpoints import auth, users, attendance, leave, departments, shifts
from backend.app.api.v1.endpoints import system_logs

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(system_logs.router, prefix="/system_log", tags=["system_log"])
router.include_router(departments.router, prefix="/departments", tags=["departments"])