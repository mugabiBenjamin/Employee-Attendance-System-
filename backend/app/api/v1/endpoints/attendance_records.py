from fastapi import APIRouter, Depends, Request, HTTPException, status
from typing import List, Optional
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.services.attendance_record_service import clock_in, clock_out, get_attendance_history
from app.models.users import Users
from app.core.security import get_current_user
from app.core.database import get_db
from app.core.config import Settings, get_settings
from app.core.utils import get_request_id
from app.schemas.attendance_record import AttendanceRecordOut, ClockInOut
from app.core.permissions import require_permissions_dependency
from app.core.enums import Permission
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attendance-records", tags=["Attendance Records"])

@router.post("/clock")
async def clock_in_out_endpoint(
    clock_data: ClockInOut,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.CLOCK_IN, Permission.CLOCK_OUT]))
) -> AttendanceRecordOut:
    """Handle clock-in or clock-out requests."""
    request_id = get_request_id(request) or "unknown"
    
    try:
        if clock_data.action == "clock_in":
            return await clock_in(request, current_user, clock_data.location, db, settings, request_id)
        elif clock_data.action == "clock_out":
            return await clock_out(request, current_user, db, settings, request_id)
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=500, detail="Unexpected error")

@router.get(
    "/history",
    response_model=List[AttendanceRecordOut],
    summary="Get attendance history",
    description="Retrieve attendance history for a user with optional date range and pagination."
)
async def get_attendance_history_endpoint(
    request: Request,
    user_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_OWN_ATTENDANCE, Permission.VIEW_ATTENDANCE]))
) -> List[AttendanceRecordOut]:
    """Retrieve attendance history for a user.

    Args:
        user_id: Optional user ID to filter attendance records (for admins/supervisors).
        start_date: Optional start date for filtering records.
        end_date: Optional end date for filtering records.
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: DEFAULT_PAGE_SIZE).
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[AttendanceRecordOut]: List of attendance records.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), database errors (500), or unexpected errors (500).
    """
    # Extract user_id early to avoid session issues in exception handlers
    current_user_id = current_user.user_id
    request_id = get_request_id(request) or "unknown"
    
    try:
        return await get_attendance_history(user_id, start_date, end_date, skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving attendance history for user_id {user_id or current_user_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user_id})
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error retrieving attendance history for user_id {user_id or current_user_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error retrieving attendance history") from e