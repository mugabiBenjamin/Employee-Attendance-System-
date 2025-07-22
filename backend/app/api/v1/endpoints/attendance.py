from typing import List, Optional
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.attendance import AttendanceCreate, AttendanceUpdate, AttendanceOut
from app.services.attendance_service import create_attendance, update_attendance, get_attendance_by_id, get_user_attendance
from app.models.user import User
from app.api.deps import get_db_session
from app.api.deps import get_current_active_user
from app.api.v1.endpoints.leave import is_manager_or_hr
from app.core.config import settings
from app.models.roles import Role, UserRoles

async def is_manager_or_hr(db: AsyncSession, user: User) -> bool:
    from sqlmodel import select
    query = select(UserRoles).join(Role).where(
        UserRoles.user_id == user.user_id,
        Role.role_name.in_(["Manager", "HR", "Admin", "Super_Admin"])
    )
    result = await db.execute(query)
    return result.first() is not None

router = APIRouter()

@router.post("/", 
    response_model=AttendanceOut, 
    status_code=status.HTTP_201_CREATED,
    summary="Clock in",
    description="Record employee clock-in time"
)
async def clock_in(
    attendance: AttendanceCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new attendance record when employee clocks in."""
    return await create_attendance(db, attendance, current_user)

@router.put("/{attendance_id}", 
    response_model=AttendanceOut,
    summary="Clock out",
    description="Update attendance record with clock-out time"
)
async def clock_out(
    attendance_id: int,
    attendance_update: AttendanceUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Update an attendance record with clock-out time."""
    return await update_attendance(db, attendance_id, attendance_update, current_user)

@router.get("/{attendance_id}", 
    response_model=AttendanceOut,
    summary="Get attendance record",
    description="Retrieve specific attendance record by ID"
)
async def get_attendance(
    attendance_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific attendance record by its ID."""
    return await get_attendance_by_id(db, attendance_id, current_user)

@router.get("/user/{user_id}", 
    response_model=List[AttendanceOut],
    summary="Get user attendance history",
    description="Retrieve attendance records for a user with optional date filtering. Users can view their own records, managers/HR can view any user's records."
)
async def get_attendance_history(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get attendance history for a specific user with optional date range filtering."""
    if user_id != current_user.user_id and not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this user's attendance")
    return await get_user_attendance(db, user_id, start_date, end_date, skip, limit)