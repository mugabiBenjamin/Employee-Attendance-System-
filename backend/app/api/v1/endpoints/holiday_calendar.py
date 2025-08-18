from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.holiday_service import (
    create_holiday,
    get_holiday,
    list_holidays,
    update_holiday,
    delete_holiday
)
from app.schemas.holiday_calendar import (
    HolidayCalendarCreate,
    HolidayCalendarUpdate,
    HolidayCalendarOut
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/holiday-calendar", tags=["Holiday Calendar"])

@router.post(
    "/",
    response_model=HolidayCalendarOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new holiday",
    description="Create a new holiday with date uniqueness check."
)
@require_permissions([Permission.CREATE_HOLIDAY])
async def create_holiday_endpoint(
    holiday: HolidayCalendarCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> HolidayCalendarOut:
    """Create a new holiday.

    Args:
        holiday: Holiday creation data.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        HolidayCalendarOut: The created holiday.
    """
    return await create_holiday(holiday, request, current_user, db)

@router.get(
    "/{holiday_id}",
    response_model=HolidayCalendarOut,
    summary="Get holiday by ID",
    description="Retrieve a holiday by its ID."
)
@require_permissions([Permission.VIEW_HOLIDAY])
async def get_holiday_endpoint(
    holiday_id: int,
    db: AsyncSession = Depends(get_db)
) -> HolidayCalendarOut:
    """Retrieve a holiday by ID.

    Args:
        holiday_id: The ID of the holiday to retrieve.
        db: Database session dependency.

    Returns:
        HolidayCalendarOut: The retrieved holiday.
    """
    return await get_holiday(holiday_id, db)

@router.get(
    "/",
    response_model=List[HolidayCalendarOut],
    summary="List all holidays",
    description="Retrieve a list of active holidays with pagination."
)
@require_permissions([Permission.VIEW_HOLIDAY])
async def list_holidays_endpoint(
    skip: int = 0,
    limit: int = 50,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[HolidayCalendarOut]:
    """List all active holidays with pagination.

    Args:
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return.
        current_user: The authenticated user.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[HolidayCalendarOut]: List of active holidays.
    """
    return await list_holidays(skip, limit, current_user, db, settings)

@router.put(
    "/{holiday_id}",
    response_model=HolidayCalendarOut,
    summary="Update a holiday",
    description="Update an existing holiday with date uniqueness check."
)
@require_permissions([Permission.UPDATE_HOLIDAY])
async def update_holiday_endpoint(
    holiday_id: int,
    holiday_update: HolidayCalendarUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> HolidayCalendarOut:
    """Update a holiday.

    Args:
        holiday_id: The ID of the holiday to update.
        holiday_update: Holiday update data.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        HolidayCalendarOut: The updated holiday.
    """
    return await update_holiday(holiday_id, holiday_update, request, current_user, db)

@router.delete(
    "/{holiday_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a holiday",
    description="Soft delete a holiday."
)
@require_permissions([Permission.DELETE_HOLIDAY])
async def delete_holiday_endpoint(
    holiday_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> None:
    """Soft delete a holiday.

    Args:
        holiday_id: The ID of the holiday to delete.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.
    """
    await delete_holiday(holiday_id, request, current_user, db)