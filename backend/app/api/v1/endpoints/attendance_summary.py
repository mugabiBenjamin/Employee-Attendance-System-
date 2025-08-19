from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import date
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.attendance_summary_service import (
    get_attendance_summary_by_user,
    get_all_attendance_summaries,
    generate_attendance_summary
)
from app.schemas.attendance_summary import AttendanceSummaryOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attendance-summary", tags=["Attendance Summary"])

@router.get(
    "/{user_id}",
    response_model=List[AttendanceSummaryOut],
    summary="Get attendance summary by user and date range",
    description="Retrieve attendance summaries for a specific user within a date range."
)
@require_permissions([Permission.VIEW_OWN_ATTENDANCE, Permission.VIEW_ALL_ATTENDANCE])
async def get_attendance_summary_endpoint(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> List[AttendanceSummaryOut]:
    """Retrieve attendance summaries for a user within a date range.

    Args:
        user_id: The ID of the user to retrieve summaries for.
        start_date: Optional start date for filtering records.
        end_date: Optional end date for filtering records.
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return.
        db: Database session dependency.
        current_user: The authenticated user.
        settings: Application settings.

    Returns:
        List[AttendanceSummaryOut]: List of attendance summaries.
    """
    return await get_attendance_summary_by_user(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
        db=db,
        settings=settings
    )

@router.get(
    "/",
    response_model=List[AttendanceSummaryOut],
    summary="Get all attendance summaries",
    description="Retrieve all attendance summaries with optional date range and pagination."
)
@require_permissions([Permission.VIEW_ALL_ATTENDANCE])
async def get_all_attendance_summaries_endpoint(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> List[AttendanceSummaryOut]:
    """Retrieve all attendance summaries with optional date range and pagination.

    Args:
        start_date: Optional start date for filtering records.
        end_date: Optional end date for filtering records.
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return.
        db: Database session dependency.
        current_user: The authenticated user.
        settings: Application settings.

    Returns:
        List[AttendanceSummaryOut]: List of attendance summaries.
    """
    return await get_all_attendance_summaries(
        skip=skip,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        db=db,
        settings=settings
    )

@router.post(
    "/generate",
    response_model=AttendanceSummaryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Generate attendance summary",
    description="Generate an attendance summary for a specific user and date."
)
@require_permissions([Permission.GENERATE_REPORTS])
async def generate_attendance_summary_endpoint(
    request: Request,
    user_id: int,
    attendance_summary_date: date,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> AttendanceSummaryOut:
    """Generate an attendance summary for a specific user and date.

    Args:
        request: The incoming HTTP request.
        user_id: The ID of the user to generate the summary for.
        attendance_summary_date: The date for the summary.
        db: Database session dependency.
        current_user: The authenticated user.
        settings: Application settings.

    Returns:
        AttendanceSummaryOut: The generated or updated attendance summary.
    """
    return await generate_attendance_summary(
        user_id=user_id,
        attendance_summary_date=attendance_summary_date,
        request=request,
        current_user=current_user,
        db=db,
        settings=settings
    )