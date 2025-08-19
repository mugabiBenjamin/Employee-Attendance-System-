from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.holiday_calendar import HolidayCalendar
from app.schemas.holiday_calendar import HolidayCalendarCreate, HolidayCalendarUpdate, HolidayCalendarOut
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import HolidayNotFoundError, DepartmentNotFoundError, ValidationError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_department_exists
from app.services.system_log_service import create_system_log
from app.schemas.system_log import SystemLogCreate
from app.models.users import Users
import logging

logger = logging.getLogger(__name__)

async def create_holiday(
    holiday: HolidayCalendarCreate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.CREATE_HOLIDAY]))
) -> HolidayCalendarOut:
    """Create a new holiday with validation, logging, and cache clearing."""
    try:
        # Validate holiday date and department
        query = select(HolidayCalendar).where(
            HolidayCalendar.holiday_date == holiday.holiday_date,
            HolidayCalendar.department_id == holiday.department_id,
            HolidayCalendar.is_active == True,
            HolidayCalendar.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ValidationError(detail="Holiday already exists for this date and department")

        if holiday.department_id:
            await validate_department_exists(db, holiday.department_id, request_id)

        db_holiday = HolidayCalendar(
            **holiday.model_dump(),
            applies_to_all=holiday.department_id is None,
            year=holiday.holiday_date.year,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_holiday)
        await db.commit()
        await db.refresh(db_holiday)

        # Invalidate cache
        await invalidate_cache_prefix("holiday_calendar")
        if holiday.department_id:
            await invalidate_cache_prefix(f"department:{holiday.department_id}")
        logger.debug(f"Cache cleared for holiday_calendar and department {holiday.department_id or 'all'}")

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_HOLIDAY,
            table_affected="holiday_calendar",
            record_id=db_holiday.holiday_id,
            old_values=None,
            new_values=db_holiday.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Holiday created, holiday_id: {db_holiday.holiday_id}, name: {db_holiday.holiday_name}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return HolidayCalendarOut.model_validate(db_holiday)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DepartmentNotFoundError as e:
        logger.error(f"Department not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating holiday: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating holiday")

async def get_holiday(
    holiday_id: int,
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_HOLIDAY]))
) -> HolidayCalendarOut:
    """Retrieve a holiday by ID."""
    try:
        if holiday_id <= 0:
            raise ValidationError(detail="Invalid holiday ID")

        cache_key = f"holiday_calendar:{holiday_id}"
        cached_holiday = await get_cache(cache_key)
        if cached_holiday:
            return HolidayCalendarOut(**cached_holiday)

        query = select(HolidayCalendar).where(
            HolidayCalendar.holiday_id == holiday_id,
            HolidayCalendar.is_active == True,
            HolidayCalendar.deleted_at == None
        )
        result = await db.execute(query)
        holiday = result.scalar_one_or_none()

        if not holiday:
            raise HolidayNotFoundError(holiday_id=holiday_id)

        holiday_dict = HolidayCalendarOut.model_validate(holiday).model_dump()
        await set_cache(cache_key, holiday_dict, ttl=300)

        logger.info(
            f"Retrieved holiday, holiday_id: {holiday_id}",
            extra={"request_id": request_id}
        )
        return HolidayCalendarOut.model_validate(holiday)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HolidayNotFoundError as e:
        logger.error(f"Holiday not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving holiday {holiday_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving holiday")

async def list_holidays(
    department_id: Optional[int] = None,
    year: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_HOLIDAY]))
) -> List[HolidayCalendarOut]:
    """Retrieve a list of active holidays with pagination and filtering."""
    try:
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")

        if year is not None and (year < 2020 or year > 2050):
            raise ValidationError(detail="Year must be between 2020 and 2050")

        if department_id:
            await validate_department_exists(db, department_id, request_id)

        cache_key = f"holiday_calendar_list:{department_id or 'all'}:{year or 'all'}:{skip}:{limit or settings.DEFAULT_PAGE_SIZE}"
        cached_holidays = await get_cache(cache_key)
        if cached_holidays:
            return [HolidayCalendarOut(**h) for h in cached_holidays]

        query = select(HolidayCalendar).where(
            HolidayCalendar.is_active == True,
            HolidayCalendar.deleted_at == None
        )
        if not any(p in current_user.permissions for p in [Permission.VIEW_HOLIDAY, Permission.MANAGE_HOLIDAYS]):
            from app.models.user_departments import UserDepartments
            query = query.join(UserDepartments, UserDepartments.user_id == current_user.user_id).where(
                (HolidayCalendar.applies_to_all == True) |
                (HolidayCalendar.department_id == UserDepartments.department_id),
                UserDepartments.is_active == True,
                UserDepartments.deleted_at == None
            )
        if department_id:
            query = query.where(
                (HolidayCalendar.applies_to_all == True) |
                (HolidayCalendar.department_id == department_id)
            )
        if year:
            query = query.where(HolidayCalendar.year == year)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        holidays = result.scalars().all()

        holidays_dict = [HolidayCalendarOut.model_validate(h).model_dump() for h in holidays]
        await set_cache(cache_key, holidays_dict, ttl=300)

        logger.info(
            f"Retrieved {len(holidays)} holidays for department_id: {department_id or 'all'}, year: {year or 'all'}",
            extra={"request_id": request_id}
        )
        return [HolidayCalendarOut.model_validate(holiday) for holiday in holidays]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DepartmentNotFoundError as e:
        logger.error(f"Department not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving holidays: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving holidays")

async def update_holiday(
    holiday_id: int,
    holiday_update: HolidayCalendarUpdate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.UPDATE_HOLIDAY]))
) -> HolidayCalendarOut:
    """Update a holiday with validation, logging, and cache clearing."""
    try:
        if holiday_id <= 0:
            raise ValidationError(detail="Invalid holiday ID")

        query = select(HolidayCalendar).where(
            HolidayCalendar.holiday_id == holiday_id,
            HolidayCalendar.is_active == True,
            HolidayCalendar.deleted_at == None
        )
        result = await db.execute(query)
        db_holiday = result.scalar_one_or_none()

        if not db_holiday:
            raise HolidayNotFoundError(holiday_id=holiday_id)

        update_data = holiday_update.model_dump(exclude_none=True)
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        if "holiday_date" in update_data:
            query = select(HolidayCalendar).where(
                HolidayCalendar.holiday_date == update_data["holiday_date"],
                HolidayCalendar.department_id == (update_data.get("department_id", db_holiday.department_id)),
                HolidayCalendar.holiday_id != holiday_id,
                HolidayCalendar.is_active == True,
                HolidayCalendar.deleted_at == None
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise ValidationError(detail="Another holiday exists for this date and department")

        if "department_id" in update_data and update_data["department_id"] is not None:
            await validate_department_exists(db, update_data["department_id"], request_id)

        old_values = db_holiday.__dict__.copy()
        if "department_id" in update_data:
            update_data["applies_to_all"] = update_data["department_id"] is None
        if "holiday_date" in update_data:
            update_data["year"] = update_data["holiday_date"].year

        for key, value in update_data.items():
            setattr(db_holiday, key, value)

        db_holiday.updated_at = datetime.now(timezone.utc)
        db.add(db_holiday)
        await db.commit()
        await db.refresh(db_holiday)

        # Invalidate cache
        await invalidate_cache_prefix("holiday_calendar")
        if db_holiday.department_id:
            await invalidate_cache_prefix(f"department:{db_holiday.department_id}")
        if old_values.get("department_id"):
            await invalidate_cache_prefix(f"department:{old_values['department_id']}")
        logger.debug(f"Cache cleared for holiday_calendar and department {db_holiday.department_id or 'all'}")

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_HOLIDAY,
            table_affected="holiday_calendar",
            record_id=holiday_id,
            old_values=old_values,
            new_values=db_holiday.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Holiday updated, holiday_id: {holiday_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return HolidayCalendarOut.model_validate(db_holiday)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (HolidayNotFoundError, DepartmentNotFoundError) as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating holiday {holiday_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating holiday")

async def delete_holiday(
    holiday_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.DELETE_HOLIDAY]))
) -> None:
    """Soft delete a holiday with logging and cache clearing."""
    try:
        if holiday_id <= 0:
            raise ValidationError(detail="Invalid holiday ID")

        query = select(HolidayCalendar).where(
            HolidayCalendar.holiday_id == holiday_id,
            HolidayCalendar.is_active == True,
            HolidayCalendar.deleted_at == None
        )
        result = await db.execute(query)
        db_holiday = result.scalar_one_or_none()

        if not db_holiday:
            raise HolidayNotFoundError(holiday_id=holiday_id)

        db_holiday.is_active = False
        db_holiday.deleted_at = datetime.now(timezone.utc)
        db_holiday.updated_at = datetime.now(timezone.utc)
        db.add(db_holiday)
        await db.commit()

        # Invalidate cache
        await invalidate_cache_prefix("holiday_calendar")
        if db_holiday.department_id:
            await invalidate_cache_prefix(f"department:{db_holiday.department_id}")
        logger.debug(f"Cache cleared for holiday_calendar and department {db_holiday.department_id or 'all'}")

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_HOLIDAY,
            table_affected="holiday_calendar",
            record_id=holiday_id,
            old_values=db_holiday.__dict__,
            new_values=None,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Holiday soft deleted, holiday_id: {holiday_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HolidayNotFoundError as e:
        logger.error(f"Holiday not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting holiday {holiday_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting holiday")