from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.time_corrections import TimeCorrections
from app.models.attendance_records import AttendanceRecords
from app.models.users import Users
from app.models.employee_hierarchy import EmployeeHierarchy
from app.schemas.time_correction import TimeCorrectionCreate, TimeCorrectionOut, TimeCorrectionUpdate
from app.core.config import Settings, get_settings
from app.core.enums import Permission, SystemAction, CorrectionStatus
from app.core.mail import send_email, EmailSchema, get_user_email
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.exceptions import TimeCorrectionNotFoundError, AttendanceRecordNotFoundError, UserNotFoundError, ValidationError, DatabaseError
from app.services.system_log_service import SystemLogService, get_system_log_service
from app.schemas.system_log import SystemLogCreate
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

async def create_time_correction(
    time_correction: TimeCorrectionCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    log_service: SystemLogService = Depends(get_system_log_service),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.CREATE_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """Create a new time correction request. Requires CREATE_TIME_CORRECTION permission."""
    try:
        # Validate attendance record exists and is active
        attendance = await _get_active_attendance(db, time_correction.attendance_id)
        if not attendance:
            raise AttendanceRecordNotFoundError(attendance_id=time_correction.attendance_id)

        # Validate user exists and is active
        user = await _get_active_user(db, time_correction.user_id)
        if not user:
            raise UserNotFoundError(user_id=time_correction.user_id)

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
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="time_corrections",
            record_id=db_time_correction.correction_id,
            old_values=None,
            new_values=db_time_correction.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent")
        )
        await log_service.create_system_log(log, current_user, request)

        logger.info(f"Time correction created: correction_id={db_time_correction.correction_id}, user_id={time_correction.user_id}")
        return TimeCorrectionOut.model_validate(db_time_correction)

    except HTTPException:
        raise
    except DatabaseError as e:
        logger.error(f"Database error creating time correction for user_id {time_correction.user_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating time correction for user_id {time_correction.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create time correction"
        )

async def get_time_correction_by_id(
    correction_id: int,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_TIME_CORRECTION]))
) -> Optional[TimeCorrectionOut]:
    """Retrieve a time correction by ID. Requires VIEW_TIME_CORRECTION permission."""
    try:
        query = select(TimeCorrections).where(TimeCorrections.correction_id == correction_id)
        result = await db.execute(query)
        correction = result.scalar_one_or_none()

        if not correction:
            raise TimeCorrectionNotFoundError(correction_id=correction_id)

        return TimeCorrectionOut.model_validate(correction)

    except TimeCorrectionNotFoundError:
        raise
    except DatabaseError as e:
        logger.error(f"Database error retrieving time correction {correction_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving time correction {correction_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve time correction"
        )

async def get_user_time_corrections(
    user_id: int,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_TIME_CORRECTION]))
) -> List[TimeCorrectionOut]:
    """Get all time corrections for a specific user. Requires VIEW_TIME_CORRECTION permission."""
    try:
        # Validate user exists
        user = await _get_active_user(db, user_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)

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

    except UserNotFoundError:
        raise
    except DatabaseError as e:
        logger.error(f"Database error retrieving time corrections for user_id {user_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving time corrections for user_id {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve time corrections"
        )

async def update_time_correction(
    correction_id: int,
    time_correction_update: TimeCorrectionUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    log_service: SystemLogService = Depends(get_system_log_service),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.UPDATE_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """Update an existing time correction. Requires UPDATE_TIME_CORRECTION permission."""
    try:
        # Get existing time correction
        query = select(TimeCorrections).where(TimeCorrections.correction_id == correction_id)
        result = await db.execute(query)
        db_correction = result.scalar_one_or_none()

        if not db_correction:
            raise TimeCorrectionNotFoundError(correction_id=correction_id)

        # Check if user is authorized (manager or HR)
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.employee_id == db_correction.user_id,
            EmployeeHierarchy.manager_id == current_user.user_id,
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none() and not current_user.has_role("HR"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this time correction"
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
            # Update attendance record if approved
            await _update_attendance_record(db, db_correction)

        db_correction.updated_at = datetime.now(timezone.utc)
        db.add(db_correction)
        await db.commit()
        await db.refresh(db_correction)

        # Send status notification if status changed
        if "status" in update_data:
            await _notify_user_of_status_change(db, db_correction, correction_id)

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE,
            table_affected="time_corrections",
            record_id=correction_id,
            old_values=old_values,
            new_values=db_correction.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent")
        )
        await log_service.create_system_log(log, current_user, request)

        logger.info(f"Time correction updated: correction_id={correction_id}")
        return TimeCorrectionOut.model_validate(db_correction)

    except HTTPException:
        raise
    except DatabaseError as e:
        logger.error(f"Database error updating time correction {correction_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating time correction {correction_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update time correction"
        )

async def delete_time_correction(
    correction_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    log_service: SystemLogService = Depends(get_system_log_service),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.DELETE_TIME_CORRECTION]))
) -> None:
    """Soft delete a time correction. Requires DELETE_TIME_CORRECTION permission."""
    try:
        query = select(TimeCorrections).where(TimeCorrections.correction_id == correction_id)
        result = await db.execute(query)
        db_correction = result.scalar_one_or_none()

        if not db_correction:
            raise TimeCorrectionNotFoundError(correction_id=correction_id)

        # Check if user is authorized (HR only)
        if not current_user.has_role("HR"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only HR can delete time corrections"
            )

        # Store values for logging before deletion
        old_values = {k: v for k, v in db_correction.__dict__.items() if not k.startswith('_')}

        # Soft delete
        db_correction.is_active = False
        db_correction.deleted_at = datetime.now(timezone.utc)
        db.add(db_correction)
        await db.commit()

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE,
            table_affected="time_corrections",
            record_id=correction_id,
            old_values=old_values,
            new_values=None,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent")
        )
        await log_service.create_system_log(log, current_user, request)

        logger.info(f"Time correction soft deleted: correction_id={correction_id}")

    except HTTPException:
        raise
    except DatabaseError as e:
        logger.error(f"Database error deleting time correction {correction_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting time correction {correction_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete time correction"
        )

# Helper functions
async def _get_active_attendance(db: AsyncSession, attendance_id: int) -> Optional[AttendanceRecords]:
    """Get active attendance record by ID."""
    try:
        query = select(AttendanceRecords).where(
            AttendanceRecords.attendance_id == attendance_id,
            AttendanceRecords.is_active == True,
            AttendanceRecords.deleted_at == None
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()
    except DatabaseError as e:
        logger.error(f"Database error retrieving attendance record {attendance_id}: {str(e)}")
        raise

async def _get_active_user(db: AsyncSession, user_id: int) -> Optional[Users]:
    """Get active user by ID."""
    try:
        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()
    except DatabaseError as e:
        logger.error(f"Database error retrieving user {user_id}: {str(e)}")
        raise

def _validate_correction_times(clock_in: Optional[datetime], clock_out: Optional[datetime]) -> None:
    """Validate that correction times are logical."""
    if clock_in and clock_out and clock_out <= clock_in:
        raise ValidationError(detail="Corrected clock-out time must be after corrected clock-in time")

async def _notify_managers_of_correction(
    db: AsyncSession,
    user_id: int,
    correction: TimeCorrections,
    user: Users
) -> None:
    """Send notification email to user's managers about new correction request."""
    try:
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.employee_id == user_id,
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
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

async def _update_attendance_record(db: AsyncSession, correction: TimeCorrections) -> None:
    """Update attendance record with approved correction times."""
    try:
        query = select(AttendanceRecords).where(
            AttendanceRecords.attendance_id == correction.attendance_id,
            AttendanceRecords.is_active == True,
            AttendanceRecords.deleted_at == None
        )
        result = await db.execute(query)
        attendance = result.scalar_one_or_none()
        if not attendance:
            raise AttendanceRecordNotFoundError(attendance_id=correction.attendance_id)
        if correction.corrected_clock_in:
            attendance.clock_in = correction.corrected_clock_in
        if correction.corrected_clock_out:
            attendance.clock_out = correction.corrected_clock_out
        attendance.updated_at = datetime.now(timezone.utc)
        db.add(attendance)
        await db.commit()
    except AttendanceRecordNotFoundError:
        raise
    except DatabaseError as e:
        logger.warning(f"Database error updating attendance record {correction.attendance_id}: {str(e)}")
        raise
    except Exception as e:
        logger.warning(f"Unexpected error updating attendance record {correction.attendance_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update attendance record {correction.attendance_id}"
        )