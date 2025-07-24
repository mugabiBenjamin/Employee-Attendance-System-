from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, date
from pydantic import BaseModel, ConfigDict
from app.models.attendance_records import AttendanceRecords
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.schemas.attendance_record import AttendanceRecordCreate, AttendanceRecordOut
from app.core.config import settings
from app.core.utils import calculate_total_hours, calculate_overtime_hours
from app.core.enums import AttendanceStatus, SystemAction
import logging
import csv
import io
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class AttendanceRecordCreateInternal(BaseModel):
    user_id: int
    clock_in_time: datetime
    ip_address: str
    location: Optional[str] = None
    status: AttendanceStatus = AttendanceStatus.PRESENT

    model_config = ConfigDict(from_attributes=True)

async def clock_in(db: AsyncSession, user: Users, ip_address: str, location: Optional[str] = None) -> AttendanceRecordOut:
    """
    Handle employee clock-in with one-click functionality, validation, and logging.
    """
    try:
        current_date = datetime.now(timezone.utc).date()
        # Check for existing active clock-in for today
        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == user.user_id,
            AttendanceRecords.date == current_date,
            AttendanceRecords.clock_out_time == None,
            AttendanceRecords.is_active == True,
            AttendanceRecords.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User already clocked in for today"
            )

        # Create attendance record
        db_record = AttendanceRecords(
            **AttendanceRecordCreateInternal(
                user_id=user.user_id,
                clock_in_time=datetime.now(timezone.utc),
                ip_address=ip_address,
                location=location
            ).model_dump(),
            date=current_date,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_record)
        await db.commit()
        await db.refresh(db_record)

        # Log action
        system_log = SystemLogs(
            user_id=user.user_id,
            action=SystemAction.CLOCK_IN,
            table_affected="attendance_records",
            record_id=db_record.attendance_id,
            old_values=None,
            new_values=db_record.__dict__,
            ip_address=ip_address,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

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
    Handle employee clock-out with validation, time calculations, and logging.
    """
    try:
        current_date = datetime.now(timezone.utc).date()
        # Find active clock-in for today
        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == user.user_id,
            AttendanceRecords.date == current_date,
            AttendanceRecords.clock_out_time == None,
            AttendanceRecords.is_active == True,
            AttendanceRecords.deleted_at == None
        )
        result = await db.execute(query)
        db_record = result.scalar_one_or_none()
        if not db_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active clock-in found for today"
            )

        # Update with clock-out time and calculate hours
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

        # Log action
        system_log = SystemLogs(
            user_id=user.user_id,
            action=SystemAction.CLOCK_OUT,
            table_affected="attendance_records",
            record_id=db_record.attendance_id,
            old_values=None,
            new_values=db_record.__dict__,
            ip_address=ip_address,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

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

async def get_attendance_history(db: AsyncSession, user: Users, start_date: Optional[date] = None, end_date: Optional[date] = None, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[AttendanceRecordOut]:
    """
    Retrieve attendance history for a user with optional date range and pagination.
    """
    try:
        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == user.user_id,
            AttendanceRecords.is_active == True,
            AttendanceRecords.deleted_at == None
        )
        if start_date:
            query = query.where(AttendanceRecords.date >= start_date)
        if end_date:
            query = query.where(AttendanceRecords.date <= end_date)

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        records = result.scalars().all()

        logger.info(f"Retrieved {len(records)} attendance records for user_id: {user.user_id}")
        return [AttendanceRecordOut.model_validate(record) for record in records]

    except Exception as e:
        logger.error(f"Error retrieving attendance history for user_id {user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving attendance history"
        )

async def export_attendance_history_csv(db: AsyncSession, user: Users, start_date: Optional[date] = None, end_date: Optional[date] = None) -> str:
    """
    Export attendance history to CSV format.
    """
    try:
        # Fetch records
        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == user.user_id,
            AttendanceRecords.is_active == True,
            AttendanceRecords.deleted_at == None
        )
        if start_date:
            query = query.where(AttendanceRecords.date >= start_date)
        if end_date:
            query = query.where(AttendanceRecords.date <= end_date)

        result = await db.execute(query)
        records = result.scalars().all()

        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Clock In", "Clock Out", "Total Hours", "Overtime Hours", "Status"])
        for record in records:
            writer.writerow([
                record.date,
                record.clock_in_time.strftime("%Y-%m-%d %H:%M:%S") if record.clock_in_time else "",
                record.clock_out_time.strftime("%Y-%m-%d %H:%M:%S") if record.clock_out_time else "",
                record.total_hours or 0,
                record.overtime_hours or 0,
                record.status.value
            ])

        logger.info(f"Exported attendance history to CSV for user_id: {user.user_id}")
        return output.getvalue()

    except Exception as e:
        logger.error(f"Error exporting attendance history for user_id {user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error exporting attendance history"
        )