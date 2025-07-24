from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, date
from pydantic import BaseModel, ConfigDict
from app.models.holiday_calendar import HolidayCalendar
from app.models.users import Users
from app.schemas.holiday_calender import HolidayCreate, HolidayUpdate, HolidayOut
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class HolidayCreateInternal(BaseModel):
    holiday_name: str
    date: date
    description: Optional[str] = None
    is_recurring: bool = False

    model_config = ConfigDict(from_attributes=True)

async def create_holiday(db: AsyncSession, holiday: HolidayCreate, current_user: Users) -> HolidayOut:
    """
    Create a new holiday with validation and logging.
    """
    try:
        # Check for existing holiday on the same date
        query = select(HolidayCalendar).where(
            HolidayCalendar.date == holiday.date,
            HolidayCalendar.is_active == True,
            HolidayCalendar.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Holiday already exists for this date"
            )

        # Create holiday
        db_holiday = HolidayCalendar(
            **HolidayCreateInternal(**holiday.model_dump()).model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_holiday)
        await db.commit()
        await db.refresh(db_holiday)

        logger.info(f"Holiday created, holiday_id: {db_holiday.holiday_id}, name: {db_holiday.holiday_name}")
        return HolidayOut.model_validate(db_holiday)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating holiday: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating holiday"
        )

async def get_holiday_by_id(db: AsyncSession, holiday_id: int) -> Optional[HolidayOut]:
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
            return None

        return HolidayOut.model_validate(holiday)

    except Exception as e:
        logger.error(f"Error retrieving holiday {holiday_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving holiday"
        )

async def get_holidays(db: AsyncSession, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[HolidayOut]:
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
        return [HolidayOut.model_validate(holiday) for holiday in holidays]

    except Exception as e:
        logger.error(f"Error retrieving holidays: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving holidays"
        )

async def update_holiday(db: AsyncSession, holiday_id: int, holiday_update: HolidayUpdate, current_user: Users) -> HolidayOut:
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
        if "date" in update_data:
            query = select(HolidayCalendar).where(
                HolidayCalendar.date == update_data["date"],
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

        # Apply updates
        for key, value in update_data.items():
            setattr(db_holiday, key, value)

        db_holiday.updated_at = datetime.now(timezone.utc)
        db.add(db_holiday)
        await db.commit()
        await db.refresh(db_holiday)

        logger.info(f"Holiday updated, holiday_id: {holiday_id}")
        return HolidayOut.model_validate(db_holiday)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating holiday {holiday_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating holiday"
        )

async def delete_holiday(db: AsyncSession, holiday_id: int, current_user: Users) -> None:
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

        logger.info(f"Holiday soft deleted, holiday_id: {holiday_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting holiday {holiday_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting holiday"
        )