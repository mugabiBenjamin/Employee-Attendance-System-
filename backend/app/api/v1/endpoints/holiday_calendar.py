from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.utils import get_request_id
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
from app.core.permissions import require_permissions_dependency
from app.core.enums import Permission

router = APIRouter(prefix="/holiday-calendar", tags=["Holiday Calendar"])

@router.post(
    "/",
    response_model=HolidayCalendarOut,
    status_code=201,
    summary="Create a new holiday"
)
async def create_holiday_endpoint(
    holiday: HolidayCalendarCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.CREATE_HOLIDAY]))
) -> HolidayCalendarOut:
    """Create a new holiday."""
    request_id = get_request_id(request)
    return await create_holiday(holiday, request, current_user, db, settings, request_id)

@router.get(
    "/{holiday_id}",
    response_model=HolidayCalendarOut,
    summary="Get holiday by ID"
)
async def get_holiday_endpoint(
    holiday_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.VIEW_HOLIDAY]))
) -> HolidayCalendarOut:
    """Retrieve a holiday by ID."""
    request_id = get_request_id(request)
    return await get_holiday(holiday_id, db, request_id)

@router.get(
    "/",
    response_model=List[HolidayCalendarOut],
    summary="List all holidays"
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
    _=Depends(require_permissions_dependency([Permission.VIEW_HOLIDAY]))
) -> List[HolidayCalendarOut]:
    """List all active holidays with optional filters and pagination."""
    request_id = get_request_id(request)
    return await list_holidays(department_id, year, skip, limit, current_user, db, settings, request_id)

@router.put(
    "/{holiday_id}",
    response_model=HolidayCalendarOut,
    summary="Update a holiday"
)
async def update_holiday_endpoint(
    holiday_id: int,
    holiday_update: HolidayCalendarUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.UPDATE_HOLIDAY]))
) -> HolidayCalendarOut:
    """Update a holiday."""
    request_id = get_request_id(request)
    return await update_holiday(holiday_id, holiday_update, request, current_user, db, settings, request_id)

@router.delete(
    "/{holiday_id}",
    status_code=204,
    summary="Delete a holiday"
)
async def delete_holiday_endpoint(
    holiday_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.DELETE_HOLIDAY]))
) -> None:
    """Soft delete a holiday."""
    request_id = get_request_id(request)
    await delete_holiday(holiday_id, request, current_user, db, settings, request_id)