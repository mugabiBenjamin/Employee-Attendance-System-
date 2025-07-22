from fastapi import APIRouter
from app.api.v1.endpoints import auth, users, attendance, leave, system_log, departments, shifts

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(attendance.router, prefix="/attendance", tags=["attendance"])
router.include_router(leave.router, prefix="/leave", tags=["leave"])
router.include_router(system_log.router, prefix="/system_log", tags=["system_log"])
router.include_router(departments.router, prefix="/departments", tags=["departments"])
router.include_router(shifts.router, prefix="/shifts", tags=["shifts"])