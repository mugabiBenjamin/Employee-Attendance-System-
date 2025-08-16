from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import date
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.attendance_summary_service import (
    get_attendance_summary_by_user,
    generate_attendance_summary
)
from app.schemas.attendance_summary import AttendanceSummaryOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attendance-summary", tags=["Attendance Summary"])

@router.get("/{user_id}", 
            response_model=List[AttendanceSummaryOut],
            summary="Get attendance summary by user and date range",
            description="Retrieve attendance summaries for a specific user within a date range.")
@require_permissions([Permission.VIEW_OWN_ATTENDANCE, Permission.VIEW_ALL_ATTENDANCE])
async def get_attendance_summary_endpoint(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[AttendanceSummaryOut]:
    """
    Retrieve attendance summary for a user within a date range by delegating to attendance_summary_service.
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

@router.post("/generate", 
            response_model=AttendanceSummaryOut,
            summary="Generate attendance summary",
            description="Generate attendance summary for a specific user and date.")
@require_permissions([Permission.GENERATE_REPORTS])
async def generate_attendance_summary_endpoint(
    user_id: int,
    date: date,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> AttendanceSummaryOut:
    """
    Generate attendance summary by delegating to attendance_summary_service.
    """
    return await generate_attendance_summary(
        user_id=user_id,
        date=date,
        request=Depends(Request),
        current_user=current_user,
        db=db,
        settings=settings
    )