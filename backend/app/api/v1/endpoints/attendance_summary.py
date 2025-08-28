from fastapi import APIRouter, Depends, Request, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import date
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions_dependency, require_attendance_view
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.utils import get_request_id
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
    description="Retrieve attendance summaries for a specific user within a date range, with optional department and active status filters."
)
@require_permissions_dependency([Permission.VIEW_OWN_ATTENDANCE, Permission.VIEW_ALL_ATTENDANCE])
async def get_attendance_summary_endpoint(
    request: Request,
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    department_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[AttendanceSummaryOut]:
    """Retrieve attendance summaries for a user within a date range.

    Args:
        user_id: The ID of the user to retrieve summaries for.
        start_date: Optional start date for filtering records.
        end_date: Optional end date for filtering records.
        department_id: Optional department ID to filter records.
        is_active: Optional filter for active/inactive summaries.
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[AttendanceSummaryOut]: List of attendance summaries.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), or server errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await get_attendance_summary_by_user(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            department_id=department_id,
            is_active=is_active,
            skip=skip,
            limit=limit,
            current_user=current_user,
            db=db,
            settings=settings,
            request_id=request_id
        )
    except HTTPException as e:
        logger.error(f"Error retrieving attendance summary for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving attendance summary for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/",
    response_model=List[AttendanceSummaryOut],
    summary="Get all attendance summaries",
    description="Retrieve all attendance summaries with optional date range, department, and active status filters."
)
@require_permissions_dependency([Permission.VIEW_ALL_ATTENDANCE])
async def get_all_attendance_summaries_endpoint(
    request: Request,
    department_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[AttendanceSummaryOut]:
    """Retrieve all attendance summaries with optional filters and pagination.

    Args:
        department_id: Optional department ID to filter records.
        start_date: Optional start date for filtering records.
        end_date: Optional end date for filtering records.
        is_active: Optional filter for active/inactive summaries.
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[AttendanceSummaryOut]: List of attendance summaries.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await get_all_attendance_summaries(
            department_id=department_id,
            start_date=start_date,
            end_date=end_date,
            is_active=is_active,
            skip=skip,
            limit=limit,
            db=db,
            settings=settings,
            request_id=request_id
        )
    except HTTPException as e:
        logger.error(f"Error retrieving all attendance summaries: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving all attendance summaries: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.post(
    "/generate",
    response_model=AttendanceSummaryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Generate attendance summary",
    description="Generate an attendance summary for a specific user and date."
)
@require_permissions_dependency([Permission.GENERATE_REPORTS])
async def generate_attendance_summary_endpoint(
    user_id: int,
    attendance_summary_date: date,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> AttendanceSummaryOut:
    """Generate an attendance summary for a specific user and date.

    Args:
        user_id: The ID of the user to generate the summary for.
        attendance_summary_date: The date for the summary.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        AttendanceSummaryOut: The generated or updated attendance summary.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await generate_attendance_summary(
            user_id=user_id,
            attendance_summary_date=attendance_summary_date,
            request=request,
            current_user=current_user,
            db=db,
            settings=settings,
            request_id=request_id
        )
    except HTTPException as e:
        logger.error(f"Error generating attendance summary for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error generating attendance summary for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")