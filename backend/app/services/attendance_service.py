from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict
from app.models.attendance_records import AttendanceRecords
from app.models.users import Users
from app.schemas.attendance_record import AttendanceRecordCreate, AttendanceRecordOut
from app.core.config import settings
from app.core.utils import calculate_total_hours, calculate_overtime_hours
from app.core.enums import AttendanceStatus
import logging

logger = logging.getLogger(__name__)

class AttendanceRecordCreateInternal(BaseModel):
    user_id: int
    clock_in_time: datetime
    ip_address: str
    location: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

async def clock_in(db: AsyncSession, user: Users, ip_address: str, location: Optional[str] = None) -> AttendanceRecordOut:
    """
    Handle employee clock-in operation with validation and logging.
    """
    try:
        # Check if user already has an active clock-in for today
        current_date = datetime.now(timezone.utc).date()
        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == user.user_id,
            AttendanceRecords.date == current_date,
            AttendanceRecords.clock_out_time == None
        )
        result = await db.execute(query)
        existing_record = result.scalar_one_or_none()
        if existing_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User already clocked in for today"
            )

        # Create new attendance record
        clock_in_data = AttendanceRecordCreateInternal(
            user_id=user.user_id,
            clock_in_time=datetime.now(timezone.utc),
            ip_address=ip_address,
            location=location
        )
        db_record = AttendanceRecords(
            user_id=clock_in_data.user_id,
            clock_in_time=clock_in_data.clock_in_time,
            date=current_date,
            status=AttendanceStatus.PRESENT,
            ip_address=clock_in_data.ip_address,
            location=clock_in_data.location,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_record)
        await db.commit()
        await db.refresh(db_record)

        logger.info(f"User clocked in, user_id: {user.user_id}, attendance_id: {db_record.attendance_id}")
        return AttendanceRecordOut.model_validate(db_record)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during clock-in for user_id {user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing clock-in"
        )

async def clock_out(db: AsyncSession, user: Users, ip_address: str) -> AttendanceRecordOut:
    """
    Handle employee clock-out operation with validation, time calculations, and logging.
    """
    try:
        # Find today's active attendance record
        current_date = datetime.now(timezone.utc).date()
        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == user.user_id,
            AttendanceRecords.date == current_date,
            AttendanceRecords.clock_out_time == None
        )
        result = await db.execute(query)
        db_record = result.scalar_one_or_none()
        if not db_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active clock-in found for today"
            )

        # Update record with clock-out time and calculated hours
        db_record.clock_out_time = datetime.now(timezone.utc)
        db_record.ip_address = ip_address
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

        logger.info(f"User clocked out, user_id: {user.user_id}, attendance_id: {db_record.attendance_id}")
        return AttendanceRecordOut.model_validate(db_record)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during clock-out for user_id {user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing clock-out"
        )