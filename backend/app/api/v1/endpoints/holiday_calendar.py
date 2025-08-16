from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.holiday_service import (
    create_holiday,
    list_holidays,
    update_holiday,
    delete_holiday
)
from app.schemas.holiday_calendar import HolidayCreate, HolidayUpdate, HolidayOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/holiday-calendar", tags=["Holiday Calendar"])

@router.post("/", 
             response_model=HolidayOut, 
             status_code=status.HTTP_201_CREATED,
             summary="Create a new holiday",
             description="Create a new holiday with date uniqueness check.")
@require_permissions([Permission.MANAGE_HOLIDAYS])
async def create_holiday_endpoint(
    holiday: HolidayCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> HolidayOut:
    """
    Create a new holiday by delegating to holiday_service.
    """
    return await create_holiday(holiday, current_user, db, settings)

@router.get("/", 
            response_model=List[HolidayOut],
            summary="List all holidays",
            description="List all active holidays with pagination.")
@require_permissions([Permission.VIEW_HOLIDAYS])
async def list_holidays_endpoint(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[HolidayOut]:
    """
    List all holidays by delegating to holiday_service.
    """
    return await list_holidays(skip, limit, current_user, db, settings)

@router.put("/{holiday_id}", 
            response_model=HolidayOut,
            summary="Update a holiday",
            description="Update an existing holiday with date uniqueness check.")
@require_permissions([Permission.MANAGE_HOLIDAYS])
async def update_holiday_endpoint(
    holiday_id: int,
    holiday_update: HolidayUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> HolidayOut:
    """
    Update a holiday by delegating to holiday_service.
    """
    return await update_holiday(holiday_id, holiday_update, current_user, db, settings)

@router.delete("/{holiday_id}", 
               status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete a holiday",
               description="Soft delete a holiday.")
@require_permissions([Permission.MANAGE_HOLIDAYS])
async def delete_holiday_endpoint(
    holiday_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> None:
    """
    Soft delete a holiday by delegating to holiday_service.
    """
    await delete_holiday(holiday_id, current_user, db, settings)