from fastapi import APIRouter
from app.api.v1.endpoints import auth, users, attendance, leave

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(attendance.router, prefix="/attendance", tags=["attendance"])
router.include_router(leave.router, prefix="/leave", tags=["leave"])