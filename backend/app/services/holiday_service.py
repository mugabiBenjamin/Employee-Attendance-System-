from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from datetime import datetime, timezone
from app.models.holiday_calendar import HolidayCalendar
from app.models.users import Users
from app.models.user_departments import UserDepartment
from app.schemas.leave import HolidayCalendarCreate, HolidayCalendarUpdate, HolidayCalendarOut
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

async def create_holiday(db: AsyncSession, holiday_create: HolidayCalendarCreate, current_user: Users) -> HolidayCalendarOut:
    try:
        # Validate department_id if provided
        if holiday_create.department_id:
            query = select(UserDepartment).where(
                UserDepartment.department_id == holiday_create.department_id,
                UserDepartment.is_active == True
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                                  detail="Department not found")
        
        # Check for duplicate holiday
        query = select(HolidayCalendar).where(
            HolidayCalendar.holiday_name == holiday_create.holiday_name,
            HolidayCalendar.holiday_date == holiday_create.holiday_date,
            HolidayCalendar.year == holiday_create.year
        )
        if holiday_create.department_id:
            query = query.where(HolidayCalendar.department_id == holiday_create.department_id)
        else:
            query = query.where(HolidayCalendar.applies_to_all == True)
        
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="Holiday already exists for this date and department")
        
        # Validate year
        if holiday_create.year < 1900 or holiday_create.year > 9999:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="Invalid year value")
        
        db_holiday = HolidayCalendar(
            **holiday_create.model_dump(),
            created_at=datetime.now(timezone.utc)
        )
        db.add(db_holiday)
        await db.commit()
        await db.refresh(db_holiday)
        
        logger.info(f"Holiday created, holiday_id {db_holiday.holiday_id}")
        return HolidayCalendarOut.model_validate(db_holiday)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating holiday: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error creating holiday")

async def get_holiday_by_id(db: AsyncSession, holiday_id: int, current_user: Users) -> Optional[HolidayCalendarOut]:
    try:
        query = select(HolidayCalendar).where(HolidayCalendar.holiday_id == holiday_id)
        result = await db.execute(query)
        holiday = result.scalar_one_or_none()
        
        if not holiday:
            return None
        
        # Check permission to view holiday
        from app.services.auth_service import check_user_permission
        has_permission = await check_user_permission(db, current_user.user_id, "view_holidays")
        if not has_permission and holiday.department_id:
            query = select(UserDepartment).where(
                UserDepartment.user_id == current_user.user_id,
                UserDepartment.department_id == holiday.department_id,
                UserDepartment.is_active == True
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none() and not holiday.applies_to_all:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                                  detail="Not authorized to view this holiday")
        
        return HolidayCalendarOut.model_validate(holiday)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving holiday: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error retrieving holiday")

async def get_holidays(db: AsyncSession, year: Optional[int] = None, 
                      department_id: Optional[int] = None, 
                      current_user: Optional[Users] = None, 
                      skip: int = 0, 
                      limit: int = settings.DEFAULT_PAGE_SIZE) -> List[HolidayCalendarOut]:
    try:
        query = select(HolidayCalendar)
        
        if year:
            query = query.where(HolidayCalendar.year == year)
        
        if department_id:
            query = query.where(
                (HolidayCalendar.department_id == department_id) | 
                (HolidayCalendar.applies_to_all == True)
            )
        
        # Restrict to user's departments if not admin
        if current_user:
            from app.services.auth_service import check_user_permission
            has_permission = await check_user_permission(db, current_user.user_id, "view_all_holidays")
            if not has_permission:
                query = query.where(
                    (HolidayCalendar.applies_to_all == True) | 
                    (HolidayCalendar.department_id.in_(
                        select(UserDepartment.department_id).where(
                            UserDepartment.user_id == current_user.user_id,
                            UserDepartment.is_active == True
                        )
                    ))
                )
        
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        holidays = result.scalars().all()
        
        logger.info(f"Retrieved {len(holidays)} holidays")
        return [HolidayCalendarOut.model_validate(h) for h in holidays]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving holidays: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error retrieving holidays")

async def update_holiday(db: AsyncSession, holiday_id: int, holiday_update: HolidayCalendarUpdate, 
                       current_user: Users) -> HolidayCalendarOut:
    try:
        query = select(HolidayCalendar).where(HolidayCalendar.holiday_id == holiday_id)
        result = await db.execute(query)
        holiday = result.scalar_one_or_none()
        
        if not holiday:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                              detail="Holiday not found")
        
        # Check permission to update holiday
        from app.services.auth_service import check_user_permission
        has_permission = await check_user_permission(db, current_user.user_id, "manage_holidays")
        if not has_permission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                              detail="Not authorized to update holidays")
        
        update_data = holiday_update.model_dump(exclude_none=True)
        
        # Validate department_id if provided
        if "department_id" in update_data and update_data["department_id"]:
            query = select(UserDepartment).where(
                UserDepartment.department_id == update_data["department_id"],
                UserDepartment.is_active == True
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                                  detail="Department not found")
        
        # Validate year if provided
        if "year" in update_data:
            if update_data["year"] < 1900 or update_data["year"] > 9999:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                                  detail="Invalid year value")
        
        # Check for duplicate holiday if name or date changed
        if "holiday_name" in update_data or "holiday_date" in update_data or "department_id" in update_data:
            query = select(HolidayCalendar).where(
                HolidayCalendar.holiday_id != holiday_id,
                HolidayCalendar.holiday_name == update_data.get("holiday_name", holiday.holiday_name),
                HolidayCalendar.holiday_date == update_data.get("holiday_date", holiday.holiday_date),
                HolidayCalendar.year == update_data.get("year", holiday.year)
            )
            if "department_id" in update_data or holiday.department_id:
                dept_id = update_data.get("department_id", holiday.department_id)
                query = query.where(
                    (HolidayCalendar.department_id == dept_id) if dept_id else (HolidayCalendar.applies_to_all == True)
                )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                                  detail="Holiday already exists for this date and department")
        
        for key, value in update_data.items():
            setattr(holiday, key, value)
        
        holiday.updated_at = datetime.now(timezone.utc)
        db.add(holiday)
        await db.commit()
        await db.refresh(holiday)
        
        logger.info(f"Holiday updated, holiday_id {holiday_id}")
        return HolidayCalendarOut.model_validate(holiday)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating holiday: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error updating holiday")

async def delete_holiday(db: AsyncSession, holiday_id: int, current_user: Users) -> None:
    try:
        query = select(HolidayCalendar).where(HolidayCalendar.holiday_id == holiday_id)
        result = await db.execute(query)
        holiday = result.scalar_one_or_none()
        
        if not holiday:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                              detail="Holiday not found")
        
        # Check permission to delete holiday
        from app.services.auth_service import check_user_permission
        has_permission = await check_user_permission(db, current_user.user_id, "manage_holidays")
        if not has_permission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                              detail="Not authorized to delete holidays")
        
        db.delete(holiday)
        await db.commit()
        
        logger.info(f"Holiday deleted, holiday_id {holiday_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting holiday: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error deleting holiday")