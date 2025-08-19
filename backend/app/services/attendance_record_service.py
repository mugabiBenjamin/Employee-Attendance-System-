from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, date
from app.models.attendance_records import AttendanceRecords
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.schemas.attendance_record import AttendanceRecordCreate, AttendanceRecordOut
from app.core.config import Settings, get_settings
from app.core.utils import calculate_total_hours, calculate_overtime_hours
from app.core.enums import SystemAction, Permission
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.exceptions import ValidationError, ResourceNotFoundError, DatabaseError, AttendanceError
import logging

logger = logging.getLogger(__name__)

async def clock_in(
    request: Request,
    user: Users = Depends(get_current_user),
    location: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.CLOCK_IN]))
) -> AttendanceRecordOut:
    """Handle employee clock-in with validation and logging."""
    try:
        current_date = datetime.now(timezone.utc).date()
        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == user.user_id,
            AttendanceRecords.date == current_date,
            AttendanceRecords.clock_out_time.is_(None),
            AttendanceRecords.is_active.is_(True)
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise AttendanceError(detail="User already clocked in for today")

        db_record = AttendanceRecords(
            **AttendanceRecordCreate(
                user_id=user.user_id,
                clock_in_time=datetime.now(timezone.utc),
                ip_address=str(request.client.host),
                location=location
            ).model_dump(),
            date=current_date,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_record)
        await db.commit()
        await db.refresh(db_record)

        system_log = SystemLogs(
            user_id=user.user_id,
            action=SystemAction.CLOCK_IN,
            table_affected="attendance_records",
            record_id=db_record.attendance_id,
            old_values=None,
            new_values=db_record.__dict__,
            ip_address=str(request.client.host),
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        await invalidate_cache_prefix(f"attendance_history:{user.user_id}")
        logger.info(f"User clocked in, user_id: {user.user_id}, attendance_id: {db_record.attendance_id}")
        return AttendanceRecordOut.model_validate(db_record)

    except AttendanceError as e:
        logger.error(f"Attendance error during clock-in for user_id {user.user_id}: {str(e)}")
        raise
    except DatabaseError as e:
        logger.error(f"Database error during clock-in for user_id {user.user_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during clock-in for user_id {user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error processing clock-in"
        )

async def clock_out(
    request: Request,
    user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.CLOCK_OUT]))
) -> AttendanceRecordOut:
    """Handle employee clock-out with validation, time calculations, and logging."""
    try:
        current_date = datetime.now(timezone.utc).date()
        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == user.user_id,
            AttendanceRecords.date == current_date,
            AttendanceRecords.clock_out_time.is_(None),
            AttendanceRecords.is_active.is_(True)
        )
        result = await db.execute(query)
        db_record = result.scalar_one_or_none()
        if not db_record:
            raise ResourceNotFoundError(resource="Attendance record", identifier="active clock-in for today")

        db_record.clock_out_time = datetime.now(timezone.utc)
        db_record.ip_address = str(request.client.host)
        total_hours = calculate_total_hours(
            clock_in=db_record.clock_in_time,
            clock_out=db_record.clock_out_time,
            break_duration=db_record.break_duration
        )
        if total_hours is not None:
            db_record.total_hours = total_hours
            db_record.overtime_hours = calculate_overtime_hours(total_hours)

        db_record.updated_at = datetime.now(timezone.utc)
        db.add(db_record)
        await db.commit()
        await db.refresh(db_record)

        system_log = SystemLogs(
            user_id=user.user_id,
            action=SystemAction.CLOCK_OUT,
            table_affected="attendance_records",
            record_id=db_record.attendance_id,
            old_values=None,
            new_values=db_record.__dict__,
            ip_address=str(request.client.host),
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        await invalidate_cache_prefix(f"attendance_history:{user.user_id}")
        logger.info(f"User clocked out, user_id: {user.user_id}, attendance_id: {db_record.attendance_id}")
        return AttendanceRecordOut.model_validate(db_record)

    except ResourceNotFoundError as e:
        logger.error(f"Resource not found during clock-out for user_id {user.user_id}: {str(e)}")
        raise
    except DatabaseError as e:
        logger.error(f"Database error during clock-out for user_id {user.user_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during clock-out for user_id {user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error processing clock-out"
        )

async def get_attendance_history(
    user: Users = Depends(get_current_user),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_OWN_ATTENDANCE]))
) -> List[AttendanceRecordOut]:
    """Retrieve attendance history for a user with date range and pagination."""
    try:
        if skip < 0 or limit <= 0:
            raise ValidationError(detail="Invalid pagination parameters")

        start_date_str = start_date.isoformat() if start_date else "none"
        end_date_str = end_date.isoformat() if end_date else "none"
        cache_key = f"attendance_history:{user.user_id}:{start_date_str}:{end_date_str}:{skip}:{limit}"

        cached_result = await get_cache(cache_key)
        if cached_result:
            return [AttendanceRecordOut(**record) for record in cached_result]

        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == user.user_id,
            AttendanceRecords.is_active.is_(True)
        )
        if start_date:
            query = query.where(AttendanceRecords.date >= start_date)
        if end_date:
            query = query.where(AttendanceRecords.date <= end_date)

        query = query.offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        result = await db.execute(query)
        records = result.scalars().all()

        records_dict = [AttendanceRecordOut.model_validate(record).model_dump() for record in records]
        await set_cache(cache_key, records_dict, ttl=300)

        logger.info(f"Retrieved {len(records)} attendance records for user_id: {user.user_id}")
        return [AttendanceRecordOut.model_validate(record) for record in records]

    except ValidationError as e:
        logger.error(f"Validation error in get_attendance_history for user_id {user.user_id}: {str(e)}")
        raise
    except DatabaseError as e:
        logger.error(f"Database error in get_attendance_history for user_id {user.user_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_attendance_history for user_id {user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error retrieving attendance history"
        )