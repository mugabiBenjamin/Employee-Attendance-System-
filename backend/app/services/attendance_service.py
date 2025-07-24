from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from sqlmodel import select
from datetime import datetime, date, timezone
from app.models.attendance_records import AttendanceRecords
from app.models.attendance_summary import AttendanceSummary
from app.models.overtime_record import OvertimeRecord
from app.models.time_correction import TimeCorrection
from app.models.users import Users
from app.schemas.attendance import AttendanceCreate, AttendanceUpdate, AttendanceOut
from app.schemas.user import TimeCorrectionUpdate, UserOut
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

async def create_attendance(db: AsyncSession, attendance_create: AttendanceCreate, current_user: Users) -> AttendanceOut:
    if attendance_create.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to clock in for another user")
    
    # Validate attendance status
    valid_statuses = ["present", "absent", "late", "early_departure", "on_leave", "half_day", "sick"]
    if attendance_create.status not in valid_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status. Must be one of {valid_statuses}")
    
    # Check for existing attendance record
    query = select(AttendanceRecords).where(AttendanceRecords.user_id == attendance_create.user_id, AttendanceRecords.date == attendance_create.date)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attendance already recorded for this date")
    
    db_attendance = AttendanceRecords(**attendance_create.model_dump())
    db.add(db_attendance)
    await db.commit()
    await db.refresh(db_attendance)
    
    logger.info(f"Attendance created for user_id {attendance_create.user_id}, attendance_id {db_attendance.attendance_id}")
    return AttendanceOut.model_validate(db_attendance)

async def update_attendance(db: AsyncSession, attendance_id: int, attendance_update: AttendanceUpdate, current_user: Users) -> AttendanceOut:
    query = select(AttendanceRecords).where(AttendanceRecords.attendance_id == attendance_id)
    result = await db.execute(query)
    attendance = result.scalar_one_or_none()
    
    if not attendance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance record not found")
    
    if attendance.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this attendance")
    
    update_data = attendance_update.model_dump(exclude_none=True)
    
    # Validate status if provided
    if "status" in update_data:
        valid_statuses = ["present", "absent", "late", "early_departure", "on_leave", "half_day", "sick"]
        if update_data["status"] not in valid_statuses:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status. Must be one of {valid_statuses}")
    
    # Calculate total hours and handle overtime
    if "clock_out_time" in update_data and update_data["clock_out_time"]:
        if update_data["clock_out_time"] <= attendance.clock_in_time:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Clock out time must be after clock in time")
        
        total_hours = (update_data["clock_out_time"] - attendance.clock_in_time).total_seconds() / 3600
        total_hours = round(total_hours - (attendance.break_duration / 60), 2)
        update_data["total_hours"] = total_hours
        
        # Calculate overtime (assuming standard shift is 8 hours)
        standard_hours = 8
        overtime_hours = max(0, total_hours - standard_hours)
        if overtime_hours > 0:
            overtime_record = OvertimeRecord(
                attendance_id=attendance_id,
                user_id=attendance.user_id,
                overtime_hours=overtime_hours,
                overtime_rate=1.5,
                overtime_amount=overtime_hours * 1.5 * 50,  # Example calculation: $50/hour base rate
                created_at=datetime.now(timezone.utc)
            )
            db.add(overtime_record)
            update_data["overtime_hours"] = overtime_hours
    
    for key, value in update_data.items():
        setattr(attendance, key, value)
    
    attendance.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(attendance)
    
    logger.info(f"Attendance updated, attendance_id {attendance_id}")
    return AttendanceOut.model_validate(attendance)

async def get_attendance_by_id(db: AsyncSession, attendance_id: int, current_user: Users) -> AttendanceOut:
    query = select(AttendanceRecords).where(AttendanceRecords.attendance_id == attendance_id)
    result = await db.execute(query)
    attendance = result.scalar_one_or_none()
    
    if not attendance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance record not found")
    
    if attendance.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this attendance")
    
    return AttendanceOut.model_validate(attendance)

async def get_user_attendance(db: AsyncSession, user_id: int, start_date: Optional[date] = None, 
                            end_date: Optional[date] = None, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[AttendanceOut]:
    query = select(AttendanceRecords).where(AttendanceRecords.user_id == user_id)
    
    if start_date:
        query = query.where(AttendanceRecords.date >= start_date)
    if end_date:
        query = query.where(AttendanceRecords.date <= end_date)
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    attendances = result.scalars().all()
    
    logger.info(f"Retrieved {len(attendances)} attendance records for user_id {user_id}")
    return [AttendanceOut.model_validate(attendance) for attendance in attendances]

async def create_time_correction(db: AsyncSession, correction: TimeCorrection, current_user: Users) -> TimeCorrection:
    if correction.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create time correction for another user")
    
    # Validate correction status
    valid_statuses = ["draft", "under_review", "approved", "rejected", "cancelled", "completed"]
    if correction.status not in valid_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status. Must be one of {valid_statuses}")
    
    # Check if at least one correction is provided
    if not correction.corrected_clock_in and not correction.corrected_clock_out:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one of corrected_clock_in or corrected_clock_out must be provided")
    
    # Validate corrected times
    if correction.corrected_clock_out and correction.corrected_clock_in:
        if correction.corrected_clock_out <= correction.corrected_clock_in:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Corrected clock out time must be after corrected clock in time")
    
    db_correction = TimeCorrection(**correction.model_dump())
    db.add(db_correction)
    await db.commit()
    await db.refresh(db_correction)
    
    logger.info(f"Time correction created for user_id {correction.user_id}, correction_id {db_correction.correction_id}")
    return db_correction

async def update_time_correction(db: AsyncSession, correction_id: int, correction_update: TimeCorrectionUpdate, current_user: Users) -> TimeCorrection:
    query = select(TimeCorrection).where(TimeCorrection.correction_id == correction_id)
    result = await db.execute(query)
    correction = result.scalar_one_or_none()
    
    if not correction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time correction not found")
    
    if correction.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this time correction")
    
    update_data = correction_update.model_dump(exclude_none=True)
    
    # Validate status if provided
    if "status" in update_data:
        valid_statuses = ["draft", "under_review", "approved", "rejected", "cancelled", "completed"]
        if update_data["status"] not in valid_statuses:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status. Must be one of {valid_statuses}")
        
        # Update approval fields if status is approved or rejected
        if update_data["status"] in ["approved", "rejected"]:
            update_data["approved_by"] = current_user.user_id
            update_data["approved_at"] = datetime.now(timezone.utc)
    
    # Validate corrected times if provided
    if "corrected_clock_out" in update_data and "corrected_clock_in" in update_data:
        if update_data["corrected_clock_out"] and update_data["corrected_clock_in"]:
            if update_data["corrected_clock_out"] <= update_data["corrected_clock_in"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Corrected clock out time must be after corrected clock in time")
    
    for key, value in update_data.items():
        setattr(correction, key, value)
    
    await db.commit()
    await db.refresh(correction)
    
    logger.info(f"Time correction updated, correction_id {correction_id}")
    return correction

async def get_time_correction_by_id(db: AsyncSession, correction_id: int, current_user: Users) -> TimeCorrection:
    query = select(TimeCorrection).where(TimeCorrection.correction_id == correction_id)
    result = await db.execute(query)
    correction = result.scalar_one_or_none()
    
    if not correction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time correction not found")
    
    if correction.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this time correction")
    
    return correction

async def refresh_attendance_summary(db: AsyncSession, current_user: Users) -> None:
    """Refresh the attendance_summary materialized view."""
    from app.api.deps import is_manager_or_hr
    if not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to refresh attendance summary")
    
    try:
        await db.execute(text("REFRESH MATERIALIZED VIEW attendance_summary"))
        await db.commit()
        logger.info("Attendance summary materialized view refreshed successfully")
    except Exception as e:
        logger.error(f"Failed to refresh attendance summary: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to refresh attendance summary")

async def get_attendance_summary(db: AsyncSession, user_id: Optional[int] = None, 
                               start_date: Optional[date] = None, end_date: Optional[date] = None,
                               department_name: Optional[str] = None, skip: int = 0, 
                               limit: int = settings.DEFAULT_PAGE_SIZE) -> List[dict]:
    """Query the attendance_summary materialized view with optional filters."""
    query = select(AttendanceSummary)
    
    if user_id:
        query = query.where(AttendanceSummary.user_id == user_id)
    if start_date:
        query = query.where(AttendanceSummary.date >= start_date)
    if end_date:
        query = query.where(AttendanceSummary.date <= end_date)
    if department_name:
        query = query.where(AttendanceSummary.department_name == department_name)
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    summaries = result.scalars().all()
    
    logger.info(f"Retrieved {len(summaries)} attendance summary records")
    return [summary.dict() for summary in summaries]

async def approve_time_correction(db: AsyncSession, correction_id: int, current_user: Users, comments: Optional[str] = None) -> TimeCorrection:
    query = select(TimeCorrection).where(TimeCorrection.correction_id == correction_id)
    result = await db.execute(query)
    correction = result.scalar_one_or_none()
    
    if not correction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time correction not found")
    
    # Check if user has permission to approve (Manager/HR/Admin)
    from app.api.deps import is_manager_or_hr
    if not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to approve time corrections")
    
    correction.status = "approved"
    correction.approved_by = current_user.user_id
    correction.approved_at = datetime.now(timezone.utc)
    correction.comments = comments
    
    # Update related attendance record if approved
    if correction.corrected_clock_in or correction.corrected_clock_out:
        query = select(AttendanceRecords).where(AttendanceRecords.attendance_id == correction.attendance_id)
        result = await db.execute(query)
        attendance = result.scalar_one_or_none()
        
        if attendance:
            if correction.corrected_clock_in:
                attendance.clock_in_time = correction.corrected_clock_in
            if correction.corrected_clock_out:
                attendance.clock_out_time = correction.corrected_clock_out
                if attendance.clock_out_time and attendance.clock_in_time:
                    total_hours = (attendance.clock_out_time - attendance.clock_in_time).total_seconds() / 3600
                    attendance.total_hours = round(total_hours - (attendance.break_duration / 60), 2)
                    
                    # Update overtime if necessary
                    standard_hours = 8
                    overtime_hours = max(0, total_hours - standard_hours)
                    if overtime_hours > 0:
                        overtime_record = OvertimeRecord(
                            attendance_id=attendance.attendance_id,
                            user_id=attendance.user_id,
                            overtime_hours=overtime_hours,
                            overtime_rate=1.5,
                            overtime_amount=overtime_hours * 1.5 * 50,  # Example calculation
                            created_at=datetime.now(timezone.utc)
                        )
                        db.add(overtime_record)
                        attendance.overtime_hours = overtime_hours
    
    await db.commit()
    await db.refresh(correction)
    
    logger.info(f"Time correction approved, correction_id {correction_id}")
    return correction

async def reject_time_correction(db: AsyncSession, correction_id: int, current_user: Users, comments: Optional[str] = None) -> TimeCorrection:
    query = select(TimeCorrection).where(TimeCorrection.correction_id == correction_id)
    result = await db.execute(query)
    correction = result.scalar_one_or_none()
    
    if not correction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time correction not found")
    
    # Check if user has permission to reject
    from app.api.deps import is_manager_or_hr
    if not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to reject time corrections")
    
    correction.status = "rejected"
    correction.approved_by = current_user.user_id
    correction.approved_at = datetime.now(timezone.utc)
    correction.comments = comments
    
    await db.commit()
    await db.refresh(correction)
    
    logger.info(f"Time correction rejected, correction_id {correction_id}")
    return correction