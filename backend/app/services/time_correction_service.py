from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.time_corrections import TimeCorrections
from app.models.attendance_records import AttendanceRecords
from app.models.users import Users
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.system_logs import SystemLogs
from app.core.mail import send_email, EmailSchema, get_user_email
from app.core.config import settings
from app.core.enums import SystemAction, CorrectionStatus
import logging
from app.schemas.time_correction import TimeCorrectionCreate, TimeCorrectionOut, TimeCorrectionUpdate

logger = logging.getLogger(__name__)

async def create_time_correction(db: AsyncSession, time_correction: TimeCorrectionCreate, current_user: Users) -> TimeCorrectionOut:
    """Create a new time correction request."""
    try:
        # Validate attendance record exists and is active
        attendance = await _get_active_attendance(db, time_correction.attendance_id)
        if not attendance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attendance record not found"
            )

        # Validate user exists and is active
        user = await _get_active_user(db, time_correction.user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Validate time correction logic
        _validate_correction_times(time_correction.corrected_clock_in, time_correction.corrected_clock_out)

        # Create time correction record
        db_time_correction = TimeCorrections(
            attendance_id=time_correction.attendance_id,
            user_id=time_correction.user_id,
            original_clock_in=time_correction.original_clock_in,
            original_clock_out=time_correction.original_clock_out,
            corrected_clock_in=time_correction.corrected_clock_in,
            corrected_clock_out=time_correction.corrected_clock_out,
            reason=time_correction.reason,
            status=time_correction.status,
            created_at=datetime.now(timezone.utc)
        )
        
        db.add(db_time_correction)
        await db.commit()
        await db.refresh(db_time_correction)

        # Send notification to managers
        await _notify_managers_of_correction(db, time_correction.user_id, db_time_correction, user)

        # Log the action
        await _log_system_action(
            db, current_user.user_id, SystemAction.INSERT, 
            "time_corrections", db_time_correction.correction_id, 
            None, db_time_correction.__dict__
        )

        logger.info(f"Time correction created: correction_id={db_time_correction.correction_id}, user_id={time_correction.user_id}")
        return TimeCorrectionOut.model_validate(db_time_correction)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating time correction for user_id {time_correction.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create time correction"
        )

async def get_time_correction_by_id(db: AsyncSession, correction_id: int) -> Optional[TimeCorrectionOut]:
    """Retrieve a time correction by ID."""
    try:
        query = select(TimeCorrections).where(TimeCorrections.correction_id == correction_id)
        result = await db.execute(query)
        correction = result.scalar_one_or_none()

        return TimeCorrectionOut.model_validate(correction) if correction else None

    except Exception as e:
        logger.error(f"Error retrieving time correction {correction_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve time correction"
        )

async def get_user_time_corrections(
    db: AsyncSession, 
    user_id: int, 
    skip: int = 0, 
    limit: int = None
) -> List[TimeCorrectionOut]:
    """Get all time corrections for a specific user."""
    try:
        # Validate user exists
        user = await _get_active_user(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        limit = limit or settings.DEFAULT_PAGE_SIZE
        
        query = (
            select(TimeCorrections)
            .where(TimeCorrections.user_id == user_id)
            .order_by(TimeCorrections.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        
        result = await db.execute(query)
        corrections = result.scalars().all()

        logger.info(f"Retrieved {len(corrections)} time corrections for user_id: {user_id}")
        return [TimeCorrectionOut.model_validate(c) for c in corrections]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving time corrections for user_id {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve time corrections"
        )

async def update_time_correction(
    db: AsyncSession, 
    correction_id: int, 
    time_correction_update: TimeCorrectionUpdate, 
    current_user: Users
) -> TimeCorrectionOut:
    """Update an existing time correction."""
    try:
        # Get existing time correction
        query = select(TimeCorrections).where(TimeCorrections.correction_id == correction_id)
        result = await db.execute(query)
        db_correction = result.scalar_one_or_none()

        if not db_correction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Time correction not found"
            )

        # Store old values for logging
        old_values = {k: v for k, v in db_correction.__dict__.items() if not k.startswith('_')}

        # Apply updates
        update_data = time_correction_update.model_dump(exclude_none=True)
        
        # Validate time logic if times are being updated
        corrected_clock_in = update_data.get("corrected_clock_in", db_correction.corrected_clock_in)
        corrected_clock_out = update_data.get("corrected_clock_out", db_correction.corrected_clock_out)
        _validate_correction_times(corrected_clock_in, corrected_clock_out)

        # Update fields
        for key, value in update_data.items():
            setattr(db_correction, key, value)

        # Handle approval workflow
        if "status" in update_data and update_data["status"] == CorrectionStatus.APPROVED:
            db_correction.approved_by = current_user.user_id
            db_correction.approved_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(db_correction)

        # Send status notification if status changed
        if "status" in update_data:
            await _notify_user_of_status_change(db, db_correction, correction_id)

        # Log the action
        await _log_system_action(
            db, current_user.user_id, SystemAction.UPDATE,
            "time_corrections", correction_id, old_values, db_correction.__dict__
        )

        logger.info(f"Time correction updated: correction_id={correction_id}")
        return TimeCorrectionOut.model_validate(db_correction)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating time correction {correction_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update time correction"
        )

async def delete_time_correction(db: AsyncSession, correction_id: int, current_user: Users) -> None:
    """Soft delete a time correction."""
    try:
        query = select(TimeCorrections).where(TimeCorrections.correction_id == correction_id)
        result = await db.execute(query)
        db_correction = result.scalar_one_or_none()

        if not db_correction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Time correction not found"
            )

        # Store values for logging before deletion
        old_values = {k: v for k, v in db_correction.__dict__.items() if not k.startswith('_')}

        # Soft delete
        await db.delete(db_correction)
        await db.commit()

        # Log the action
        await _log_system_action(
            db, current_user.user_id, SystemAction.DELETE,
            "time_corrections", correction_id, old_values, None
        )

        logger.info(f"Time correction deleted: correction_id={correction_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting time correction {correction_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete time correction"
        )

# Helper functions
async def _get_active_attendance(db: AsyncSession, attendance_id: int) -> Optional[AttendanceRecords]:
    """Get active attendance record by ID."""
    query = select(AttendanceRecords).where(AttendanceRecords.attendance_id == attendance_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def _get_active_user(db: AsyncSession, user_id: int) -> Optional[Users]:
    """Get active user by ID."""
    query = select(Users).where(
        Users.user_id == user_id,
        Users.is_active == True,
        Users.deleted_at == None
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()

def _validate_correction_times(clock_in: Optional[datetime], clock_out: Optional[datetime]) -> None:
    """Validate that correction times are logical."""
    if clock_in and clock_out and clock_out <= clock_in:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Corrected clock-out time must be after corrected clock-in time"
        )

async def _notify_managers_of_correction(
    db: AsyncSession, 
    user_id: int, 
    correction: TimeCorrections, 
    user: Users
) -> None:
    """Send notification email to user's managers about new correction request."""
    try:
        query = select(EmployeeHierarchy).where(EmployeeHierarchy.employee_id == user_id)
        result = await db.execute(query)
        hierarchies = result.scalars().all()

        for hierarchy in hierarchies:
            manager_email = await get_user_email(hierarchy.manager_id, db)
            if manager_email:
                email_data = EmailSchema(
                    to_email=manager_email,
                    subject=f"New Time Correction Request (ID: {correction.correction_id})",
                    body=(
                        f"A new time correction request has been submitted.\n\n"
                        f"Employee: {user.first_name} {user.last_name} ({user.email})\n"
                        f"Attendance ID: {correction.attendance_id}\n"
                        f"Reason: {correction.reason}\n"
                        f"Status: {correction.status.value}\n\n"
                        f"Please review and take appropriate action."
                    )
                )
                await send_email(email_data)
    except Exception as e:
        logger.warning(f"Failed to send manager notification: {str(e)}")

async def _notify_user_of_status_change(db: AsyncSession, correction: TimeCorrections, correction_id: int) -> None:
    """Send notification to user when correction status changes."""
    try:
        user_email = await get_user_email(correction.user_id, db)
        if user_email:
            status_text = correction.status.value.replace('_', ' ').title()
            email_data = EmailSchema(
                to_email=user_email,
                subject=f"Time Correction {status_text} (ID: {correction_id})",
                body=(
                    f"Dear User,\n\n"
                    f"Your time correction request (ID: {correction_id}) has been {status_text.lower()}.\n\n"
                    f"Details:\n"
                    f"Reason: {correction.reason}\n"
                    f"Status: {status_text}\n\n"
                    f"Please contact HR if you have any questions.\n\n"
                    f"Best regards,\nEmployee Management System"
                )
            )
            await send_email(email_data)
    except Exception as e:
        logger.warning(f"Failed to send user notification: {str(e)}")

async def _log_system_action(
    db: AsyncSession,
    user_id: int,
    action: SystemAction,
    table_name: str,
    record_id: int,
    old_values: Optional[dict],
    new_values: Optional[dict]
) -> None:
    """Log system action to audit trail."""
    try:
        system_log = SystemLogs(
            user_id=user_id,
            action=action,
            table_affected=table_name,
            record_id=record_id,
            old_values=old_values,
            new_values=new_values,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()
    except Exception as e:
        logger.warning(f"Failed to log system action: {str(e)}")