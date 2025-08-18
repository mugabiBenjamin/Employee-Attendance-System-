from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.holiday_calendar import HolidayCalendar
from app.models.users import Users
from app.models.departments import Departments
from app.models.system_logs import SystemLogs
from app.schemas.holiday_calendar import HolidayCalendarCreate, HolidayCalendarUpdate, HolidayCalendarOut
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import HolidayNotFoundError, DepartmentNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

async def create_holiday(
    holiday: HolidayCalendarCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.CREATE_HOLIDAY]))
) -> HolidayCalendarOut:
    """Create a new holiday with validation and logging."""
    try:
        query = select(HolidayCalendar).where(
            HolidayCalendar.holiday_date == holiday.date,
            HolidayCalendar.is_active.is_(True),
            HolidayCalendar.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Holiday already exists for this date"
            )

        if holiday.department_id:
            query = select(Departments).where(
                Departments.department_id == holiday.department_id,
                Departments.is_active.is_(True),
                Departments.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise DepartmentNotFoundError(dept_id=holiday.department_id)

        db_holiday = HolidayCalendar(
            **holiday.model_dump(),
            applies_to_all=holiday.department_id is None,
            year=holiday.date.year,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_holiday)
        await db.commit()
        await db.refresh(db_holiday)

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_HOLIDAY,
            table_affected="holiday_calendar",
            record_id=db_holiday.holiday_id,
            old_values=None,
            new_values=db_holiday.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Holiday created, holiday_id: {db_holiday.holiday_id}, name: {db_holiday.holiday_name}")
        return HolidayCalendarOut.model_validate(db_holiday)

    except (HTTPException, DepartmentNotFoundError):
        raise
    except Exception as e:
        logger.error(f"Error creating holiday: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating holiday"
        )

async def get_holiday(
    holiday_id: int,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.VIEW_HOLIDAY]))
) -> HolidayCalendarOut:
    """Retrieve a holiday by ID."""
    try:
        query = select(HolidayCalendar).where(
            HolidayCalendar.holiday_id == holiday_id,
            HolidayCalendar.is_active.is_(True),
            HolidayCalendar.deleted_at.is_(None)
        )
        result = await db.execute(query)
        holiday = result.scalar_one_or_none()

        if not holiday:
            raise HolidayNotFoundError(holiday_id=holiday_id)

        return HolidayCalendarOut.model_validate(holiday)

    except HolidayNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error retrieving holiday {holiday_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving holiday"
        )

async def list_holidays(
    skip: int = 0,
    limit: int = 50,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_HOLIDAY]))
) -> List[HolidayCalendarOut]:
    """Retrieve a list of active holidays with pagination."""
    try:
        query = select(HolidayCalendar).where(
            HolidayCalendar.is_active.is_(True),
            HolidayCalendar.deleted_at.is_(None)
        )
        if not any(p in current_user.permissions for p in [Permission.VIEW_HOLIDAY, Permission.MANAGE_HOLIDAYS]) and current_user.department_id:
            query = query.where(
                (HolidayCalendar.applies_to_all.is_(True)) |
                (HolidayCalendar.department_id == current_user.department_id)
            )

        query = query.offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        result = await db.execute(query)
        holidays = result.scalars().all()

        logger.info(f"Retrieved {len(holidays)} holidays")
        return [HolidayCalendarOut.model_validate(holiday) for holiday in holidays]

    except Exception as e:
        logger.error(f"Error retrieving holidays: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving holidays"
        )

async def update_holiday(
    holiday_id: int,
    holiday_update: HolidayCalendarUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.UPDATE_HOLIDAY]))
) -> HolidayCalendarOut:
    """Update a holiday with validation and logging."""
    try:
        query = select(HolidayCalendar).where(
            HolidayCalendar.holiday_id == holiday_id,
            HolidayCalendar.is_active.is_(True),
            HolidayCalendar.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_holiday = result.scalar_one_or_none()

        if not db_holiday:
            raise HolidayNotFoundError(holiday_id=holiday_id)

        update_data = holiday_update.model_dump(exclude_none=True)
        if "holiday_date" in update_data:
            query = select(HolidayCalendar).where(
                HolidayCalendar.holiday_date == update_data["holiday_date"],
                HolidayCalendar.holiday_id != holiday_id,
                HolidayCalendar.is_active.is_(True),
                HolidayCalendar.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Another holiday exists for this date"
                )

        if "department_id" in update_data and update_data["department_id"] is not None:
            query = select(Departments).where(
                Departments.department_id == update_data["department_id"],
                Departments.is_active.is_(True),
                Departments.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise DepartmentNotFoundError(dept_id=update_data["department_id"])

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

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_HOLIDAY,
            table_affected="holiday_calendar",
            record_id=holiday_id,
            old_values=old_values,
            new_values=db_holiday.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Holiday updated, holiday_id: {holiday_id}")
        return HolidayCalendarOut.model_validate(db_holiday)

    except (HolidayNotFoundError, DepartmentNotFoundError, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error updating holiday {holiday_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating holiday"
        )

async def delete_holiday(
    holiday_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.DELETE_HOLIDAY]))
) -> None:
    """Soft delete a holiday with logging."""
    try:
        query = select(HolidayCalendar).where(
            HolidayCalendar.holiday_id == holiday_id,
            HolidayCalendar.is_active.is_(True),
            HolidayCalendar.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_holiday = result.scalar_one_or_none()

        if not db_holiday:
            raise HolidayNotFoundError(holiday_id=holiday_id)

        db_holiday.is_active = False
        db_holiday.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_HOLIDAY,
            table_affected="holiday_calendar",
            record_id=holiday_id,
            old_values=db_holiday.__dict__,
            new_values=None,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Holiday soft deleted, holiday_id: {holiday_id}")

    except HolidayNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error deleting holiday {holiday_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting holiday"
        )