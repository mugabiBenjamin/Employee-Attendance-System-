from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from datetime import date
from app.schemas.attendance import AttendanceCreate, AttendanceUpdate, AttendanceOut
from app.services.attendance_service import create_attendance, update_attendance, get_attendance_by_id, get_user_attendance
from app.api.deps import get_db_session, get_current_active_user
from app.models.user import User
from app.models.roles import UserRoles, Role  # Changed: Import user_roles and roles from app.models.roles
from app.core.config import settings

router = APIRouter()

@router.post("/", response_model=AttendanceOut, status_code=status.HTTP_201_CREATED)
async def clock_in(
    attendance: AttendanceCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    return await create_attendance(db, attendance, current_user)

@router.put("/{attendance_id}", response_model=AttendanceOut)
async def clock_out(
    attendance_id: int,
    attendance_update: AttendanceUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    return await update_attendance(db, attendance_id, attendance_update, current_user)

@router.get("/{attendance_id}", response_model=AttendanceOut)
async def get_attendance(
    attendance_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    return await get_attendance_by_id(db, attendance_id, current_user)

@router.get("/user/{user_id}", response_model=List[AttendanceOut])
async def get_attendance_history(
    user_id: int,
    start_date: date = None,
    end_date: date = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    if user_id != current_user.user_id and not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this user's attendance")
    return await get_user_attendance(db, user_id, start_date, end_date, skip, limit)

async def is_manager_or_hr(db: AsyncSession, user: User) -> bool:
    from sqlmodel import select
    query = select(UserRoles).join(Role).where(
        UserRoles.user_id == user.user_id,
        Role.role_name.in_(["Manager", "HR", "Admin", "Super_Admin"])
    )
    result = await db.execute(query)
    return result.first() is not None