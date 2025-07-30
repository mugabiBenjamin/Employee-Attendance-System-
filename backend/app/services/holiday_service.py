from typing import List, Optional
from fastapi import HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, date
from app.models.holiday_calendar import HolidayCalendar
from app.models.users import Users
from app.models.departments import Departments
from app.models.system_logs import SystemLogs
from app.schemas.holiday_calendar import HolidayCalendarCreate, HolidayCalendarUpdate, HolidayCalendarOut
from app.core.config import settings
from app.core.enums import SystemAction
from app.core.exceptions import DepartmentNotFoundError
from app.core.security import get_current_user
from app.core.permissions import check_permission
import logging

logger = logging.getLogger(__name__)

async def create_holiday(
    db: AsyncSession,
    holiday: HolidayCalendarCreate,
    current_user: Users = Depends(get_current_user),
    _: str = Depends(check_permission("create_holiday"))
) -> HolidayCalendarOut:
    """
    Create a new holiday with validation and logging.
    """
    try:
        # Check for existing holiday on the same date
        query = select(HolidayCalendar).where(
            HolidayCalendar.holiday_date == holiday.date,
            HolidayCalendar.is_active == True,
            HolidayCalendar.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Holiday already exists for this date"
            )

        # Validate department_id if provided
        if holiday.department_id:
            query = select(Departments).where(
                Departments.department_id == holiday.department_id,
                Departments.is_active == True,
                Departments.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise DepartmentNotFoundError()

        # Create holiday
        db_holiday = HolidayCalendar(
            holiday_name=holiday.holiday_name,
            holiday_date=holiday.date,
            is_recurring=holiday.is_recurring,
            applies_to_all=holiday.department_id is None,
            department_id=holiday.department_id,
            year=holiday.date.year,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_holiday)
        await db.commit()
        await db.refresh(db_holiday)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="holiday_calendar",
            record_id=db_holiday.holiday_id,
            old_values=None,
            new_values=db_holiday.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Holiday created, holiday_id: {db_holiday.holiday_id}, name: {db_holiday.holiday_name}")
        return HolidayCalendarOut.model_validate(db_holiday)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating holiday: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating holiday"
        )

async def get_holiday_by_id(
    db: AsyncSession,
    holiday_id: int,
    _: str = Depends(check_permission("view_holiday"))
) -> Optional[HolidayCalendarOut]:
    """
    Retrieve a holiday by ID.
    """
    try:
        query = select(HolidayCalendar).where(
            HolidayCalendar.holiday_id == holiday_id,
            HolidayCalendar.is_active == True,
            HolidayCalendar.deleted_at == None
        )
        result = await db.execute(query)
        holiday = result.scalar_one_or_none()

        if not holiday:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Holiday not found"
            )

        return HolidayCalendarOut.model_validate(holiday)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving holiday {holiday_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving holiday"
        )

async def get_holidays(
    db: AsyncSession,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    _: str = Depends(check_permission("view_holiday"))
) -> List[HolidayCalendarOut]:
    """
    Retrieve a list of active holidays with pagination.
    """
    try:
        query = select(HolidayCalendar).where(
            HolidayCalendar.is_active == True,
            HolidayCalendar.deleted_at == None
        ).offset(skip).limit(limit)
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
    db: AsyncSession,
    holiday_id: int,
    holiday_update: HolidayCalendarUpdate,
    current_user: Users = Depends(get_current_user),
    _: str = Depends(check_permission("update_holiday"))
) -> HolidayCalendarOut:
    """
    Update a holiday with validation and logging.
    """
    try:
        # Retrieve holiday
        query = select(HolidayCalendar).where(
            HolidayCalendar.holiday_id == holiday_id,
            HolidayCalendar.is_active == True,
            HolidayCalendar.deleted_at == None
        )
        result = await db.execute(query)
        db_holiday = result.scalar_one_or_none()

        if not db_holiday:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Holiday not found"
            )

        # Check for duplicate date if updated
        update_data = holiday_update.model_dump(exclude_none=True)
        if "holiday_date" in update_data:
            query = select(HolidayCalendar).where(
                HolidayCalendar.holiday_date == update_data["holiday_date"],
                HolidayCalendar.holiday_id != holiday_id,
                HolidayCalendar.is_active == True,
                HolidayCalendar.deleted_at == None
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Another holiday exists for this date"
                )

        # Validate department_id if provided
        if "department_id" in update_data and update_data["department_id"] is not None:
            query = select(Departments).where(
                Departments.department_id == update_data["department_id"],
                Departments.is_active == True,
                Departments.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise DepartmentNotFoundError()

        # Update applies_to_all and year if necessary
        if "department_id" in update_data:
            update_data["applies_to_all"] = update_data["department_id"] is None
        if "holiday_date" in update_data:
            update_data["year"] = update_data["holiday_date"].year

        # Apply updates
        for key, value in update_data.items():
            setattr(db_holiday, key, value)

        db_holiday.updated_at = datetime.now(timezone.utc)
        db.add(db_holiday)
        await db.commit()
        await db.refresh(db_holiday)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE,
            table_affected="holiday_calendar",
            record_id=holiday_id,
            old_values=None,
            new_values=db_holiday.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Holiday updated, holiday_id: {holiday_id}")
        return HolidayCalendarOut.model_validate(db_holiday)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating holiday {holiday_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating holiday"
        )

async def delete_holiday(
    db: AsyncSession,
    holiday_id: int,
    current_user: Users = Depends(get_current_user),
    _: str = Depends(check_permission("delete_holiday"))
) -> None:
    """
    Soft delete a holiday with logging.
    """
    try:
        query = select(HolidayCalendar).where(
            HolidayCalendar.holiday_id == holiday_id,
            HolidayCalendar.is_active == True,
            HolidayCalendar.deleted_at == None
        )
        result = await db.execute(query)
        db_holiday = result.scalar_one_or_none()

        if not db_holiday:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Holiday not found"
            )

        db_holiday.is_active = False
        db_holiday.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.DELETE,
            table_affected="holiday_calendar",
            record_id=holiday_id,
            old_values=db_holiday.__dict__,
            new_values=None,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Holiday soft deleted, holiday_id: {holiday_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting holiday {holiday_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting holiday"
        )