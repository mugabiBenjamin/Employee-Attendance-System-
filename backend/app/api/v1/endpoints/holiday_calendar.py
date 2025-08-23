from fastapi import APIRouter, Depends, status, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.services.holiday_calendar_service import (
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
from app.core.permissions import require_permissions
from app.core.enums import Permission
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/holiday-calendar", tags=["Holiday Calendar"])

@router.post(
    "/",
    response_model=HolidayCalendarOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new holiday",
    description="Create a new holiday with date and department uniqueness check."
)
async def create_holiday_endpoint(
    holiday: HolidayCalendarCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.CREATE_HOLIDAY]))
) -> HolidayCalendarOut:
    """Create a new holiday.

    Args:
        holiday: The holiday data to create.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        HolidayCalendarOut: The created holiday.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await create_holiday(holiday, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error creating holiday: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating holiday: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/{holiday_id}",
    response_model=HolidayCalendarOut,
    summary="Get holiday by ID",
    description="Retrieve a holiday by its ID."
)
async def get_holiday_endpoint(
    holiday_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.VIEW_HOLIDAY]))
) -> HolidayCalendarOut:
    """Retrieve a holiday by ID.

    Args:
        holiday_id: The ID of the holiday to retrieve.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.

    Returns:
        HolidayCalendarOut: The retrieved holiday.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await get_holiday(holiday_id, db, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving holiday {holiday_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving holiday {holiday_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/",
    response_model=List[HolidayCalendarOut],
    summary="List all holidays",
    description="Retrieve a list of active holidays, optionally filtered by department or year with pagination."
)
async def list_holidays_endpoint(
    request: Request,
    department_id: Optional[int] = None,
    year: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_HOLIDAY]))
) -> List[HolidayCalendarOut]:
    """List all active holidays with optional filters and pagination.

    Args:
        department_id: Optional department ID to filter holidays.
        year: Optional year to filter holidays.
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: DEFAULT_PAGE_SIZE).
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[HolidayCalendarOut]: List of holidays.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await list_holidays(department_id, year, skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error listing holidays: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing holidays: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{holiday_id}",
    response_model=HolidayCalendarOut,
    summary="Update a holiday",
    description="Update an existing holiday with date and department uniqueness check."
)
async def update_holiday_endpoint(
    holiday_id: int,
    holiday_update: HolidayCalendarUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.UPDATE_HOLIDAY]))
) -> HolidayCalendarOut:
    """Update a holiday.

    Args:
        holiday_id: The ID of the holiday to update.
        holiday_update: The updated holiday data.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        HolidayCalendarOut: The updated holiday.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await update_holiday(holiday_id, holiday_update, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error updating holiday {holiday_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating holiday {holiday_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{holiday_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a holiday",
    description="Soft delete a holiday."
)
async def delete_holiday_endpoint(
    holiday_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.DELETE_HOLIDAY]))
) -> None:
    """Soft delete a holiday.

    Args:
        holiday_id: The ID of the holiday to delete.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        None: No content returned on successful deletion.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        await delete_holiday(holiday_id, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error deleting holiday {holiday_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting holiday {holiday_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")