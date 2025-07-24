from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.schemas.attendance_record import AttendanceCreate, AttendanceUpdate, AttendanceOut
from app.schemas.user import TimeCorrectionCreate, TimeCorrectionUpdate, TimeCorrectionOut
from app.services.attendance_service import (
    create_attendance,
    refresh_attendance_summary, 
    update_attendance, 
    get_attendance_by_id, 
    get_user_attendance, 
    create_time_correction, 
    update_time_correction, 
    get_time_correction_by_id, 
    get_attendance_summary, 
    approve_time_correction, 
    reject_time_correction
)
from app.models.users import Users
from app.api.deps import get_db_session, get_current_active_user
from app.services.auth_service import check_user_permission
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

async def is_manager_or_hr(db: AsyncSession, user: Users) -> bool:
    from sqlmodel import select
    from app.models.user_roles import UserRoles
    from app.models.user_roles import Roles
    query = select(UserRoles).join(Roles).where(
        UserRoles.user_id == user.user_id,
        UserRoles.is_active == True,
        Roles.role_name.in_(["Manager", "HR", "Admin", "Super_Admin"])
    )
    result = await db.execute(query)
    return result.first() is not None

@router.post("/", 
    response_model=AttendanceOut, 
    status_code=status.HTTP_201_CREATED,
    summary="Clock in",
    description="Record employee clock-in time with validated status"
)
async def clock_in(
    attendance: AttendanceCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Create a new attendance record when employee clocks in."""
    valid_statuses = ["present", "late", "on_leave", "sick", "absent"]
    if attendance.status not in valid_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                          detail=f"Invalid status. Must be one of {valid_statuses} for clock-in")
    return await create_attendance(db, attendance, current_user)

@router.put("/{attendance_id}", 
    response_model=AttendanceOut,
    summary="Clock out",
    description="Update attendance record with clock-out time and status"
)
async def clock_out(
    attendance_id: int,
    attendance_update: AttendanceUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Update an attendance record with clock-out time."""
    if attendance_update.status:
        valid_statuses = ["present", "early_departure", "half_day", "absent"]
        if attendance_update.status not in valid_statuses:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"Invalid status. Must be one of {valid_statuses} for clock-out")
    return await update_attendance(db, attendance_id, attendance_update, current_user)

@router.get("/{attendance_id}", 
    response_model=AttendanceOut,
    summary="Get attendance record",
    description="Retrieve specific attendance record by ID"
)
async def get_attendance(
    attendance_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
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
    current_user: Users = Depends(get_current_active_user)
):
    """Get attendance history for a specific user with optional date range filtering."""
    if user_id != current_user.user_id and not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to view this user's attendance")
    return await get_user_attendance(db, user_id, start_date, end_date, skip, limit)

@router.post("/time-correction", 
    response_model=TimeCorrectionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create time correction",
    description="Create a new time correction request for an attendance record"
)
async def create_time_correction_request(
    correction: TimeCorrectionCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Create a new time correction request."""
    valid_statuses = ["draft", "under_review"]
    if correction.status not in valid_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                          detail=f"Invalid status. Must be one of {valid_statuses} for time correction creation")
    return await create_time_correction(db, correction, current_user)

@router.put("/time-correction/{correction_id}", 
    response_model=TimeCorrectionOut,
    summary="Update time correction",
    description="Update an existing time correction request"
)
async def update_time_correction_request(
    correction_id: int,
    correction_update: TimeCorrectionUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Update a time correction request."""
    if correction_update.status:
        valid_statuses = ["draft", "under_review", "cancelled"]
        if correction_update.status not in valid_statuses:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"Invalid status. Must be one of {valid_statuses} for time correction update")
    return await update_time_correction(db, correction_id, correction_update, current_user)

@router.get("/time-correction/{correction_id}", 
    response_model=TimeCorrectionOut,
    summary="Get time correction",
    description="Retrieve specific time correction by ID"
)
async def get_time_correction(
    correction_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Get a specific time correction by its ID."""
    correction = await get_time_correction_by_id(db, correction_id, current_user)
    return correction

@router.post("/time-correction/{correction_id}/approve", 
    response_model=TimeCorrectionOut,
    summary="Approve time correction",
    description="Approve a time correction request"
)
async def approve_time_correction_request(
    correction_id: int,
    comments: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Approve a time correction request."""
    if not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to approve time corrections")
    return await approve_time_correction(db, correction_id, current_user, comments)

@router.post("/time-correction/{correction_id}/reject", 
    response_model=TimeCorrectionOut,
    summary="Reject time correction",
    description="Reject a time correction request"
)
async def reject_time_correction_request(
    correction_id: int,
    comments: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Reject a time correction request."""
    if not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to reject time corrections")
    return await reject_time_correction(db, correction_id, current_user, comments)

@router.post("/refresh-summary", status_code=status.HTTP_204_NO_CONTENT, summary="Refresh attendance summary", description="Refresh the attendance_summary materialized view")
async def refresh_attendance_summary_endpoint(
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Refresh the attendance summary materialized view."""
    await refresh_attendance_summary(db, current_user)
    return None

@router.get("/summary", 
    response_model=List[dict],
    summary="Get attendance summary",
    description="Query attendance summary from materialized view with optional filters"
)
async def get_attendance_summary_report(
    user_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    department_name: Optional[str] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Get attendance summary report from materialized view."""
    has_permission = await check_user_permission(db, current_user.user_id, "view_attendance_reports")
    if not has_permission:
        if user_id and user_id != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                              detail="Not authorized to view other users' attendance summary")
        user_id = current_user.user_id
        
    return await get_attendance_summary(db, user_id, start_date, end_date, department_name, skip, limit)

@router.get("/overtime/{user_id}", 
    response_model=List[AttendanceOut],
    summary="Get overtime records",
    description="Retrieve overtime records for a user with optional date filtering"
)
async def get_overtime_records(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Get overtime records for a specific user."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_overtime")
    if user_id != current_user.user_id and not has_permission:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to view overtime records")
    
    # Query attendance records with non-zero overtime_hours
    attendance_records = await get_user_attendance(db, user_id, start_date, end_date, skip, limit)
    overtime_records = [record for record in attendance_records if record.overtime_hours > 0]
    
    logger.info(f"Retrieved {len(overtime_records)} overtime records for user_id {user_id}")
    return overtime_records