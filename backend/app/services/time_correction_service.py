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
from app.services.system_log_service import create_system_log
from app.schemas.system_log import SystemLogCreate
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

async def create_time_correction(
    time_correction: TimeCorrectionCreate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.CREATE_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """
    Create a new time correction request with validation and logging."""
    try:
        # Validate attendance record exists and is active
        attendance = await _get_active_attendance(db, time_correction.attendance_id, request_id)
        if not attendance:
            raise AttendanceRecordNotFoundError(attendance_id=time_correction.attendance_id)

        # Validate user exists and is active
        user = await _get_active_user(db, time_correction.user_id, request_id)
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
        await _notify_managers_of_correction(db, time_correction.user_id, db_time_correction, user, request_id)

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="time_corrections",
            record_id=db_time_correction.correction_id,
            old_values=None,
            new_values=db_time_correction.__dict__,
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Time correction created: correction_id={db_time_correction.correction_id}, user_id={time_correction.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return TimeCorrectionOut.model_validate(db_time_correction)

    except AttendanceRecordNotFoundError as e:
        logger.error(f"Attendance record not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error creating time correction: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error creating time correction: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_time_correction(
    correction_id: int,
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """
    Retrieve a time correction by ID."""
    try:
        query = select(TimeCorrections).where(
            TimeCorrections.correction_id == correction_id,
            TimeCorrections.is_active == True,
            TimeCorrections.deleted_at == None
        )
        result = await db.execute(query)
        correction = result.scalar_one_or_none()

        if not correction:
            raise TimeCorrectionNotFoundError(correction_id=correction_id)

        logger.info(
            f"Retrieved time correction: correction_id={correction_id}",
            extra={"request_id": request_id}
        )
        return TimeCorrectionOut.model_validate(correction)

    except TimeCorrectionNotFoundError as e:
        logger.error(f"Time correction not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_user_time_corrections(
    user_id: int,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_TIME_CORRECTION]))
) -> List[TimeCorrectionOut]:
    """
    Retrieve all time corrections for a specific user with pagination."""
    try:
        # Validate user exists
        user = await _get_active_user(db, user_id, request_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        
        query = (
            select(TimeCorrections)
            .where(
                TimeCorrections.user_id == user_id,
                TimeCorrections.is_active == True,
                TimeCorrections.deleted_at == None
            )
            .order_by(TimeCorrections.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        
        result = await db.execute(query)
        corrections = result.scalars().all()

        logger.info(
            f"Retrieved {len(corrections)} time corrections for user_id: {user_id}",
            extra={"request_id": request_id}
        )
        return [TimeCorrectionOut.model_validate(c) for c in corrections]

    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving time corrections for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving time corrections for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def update_time_correction(
    correction_id: int,
    time_correction_update: TimeCorrectionUpdate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.UPDATE_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """
    Update an existing time correction with validation and logging."""
    try:
        # Get existing time correction
        query = select(TimeCorrections).where(
            TimeCorrections.correction_id == correction_id,
            TimeCorrections.is_active == True,
            TimeCorrections.deleted_at == None
        )
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

        # Validate update data
        update_data = time_correction_update.model_dump(exclude_none=True)
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        # Validate time logic if times are being updated
        corrected_clock_in = update_data.get("corrected_clock_in", db_correction.corrected_clock_in)
        corrected_clock_out = update_data.get("corrected_clock_out", db_correction.corrected_clock_out)
        _validate_correction_times(corrected_clock_in, corrected_clock_out)

        # Store old values for logging
        old_values = db_correction.__dict__.copy()

        # Apply updates
        for key, value in update_data.items():
            setattr(db_correction, key, value)

        # Handle approval workflow
        if update_data.get("status") == CorrectionStatus.APPROVED:
            db_correction.approved_by = current_user.user_id
            db_correction.approved_at = datetime.now(timezone.utc)
            # Update attendance record if approved
            await _update_attendance_record(db, db_correction, request_id)

        db_correction.updated_at = datetime.now(timezone.utc)
        db.add(db_correction)
        await db.commit()
        await db.refresh(db_correction)

        # Send status notification if status changed
        if "status" in update_data:
            await _notify_user_of_status_change(db, db_correction, correction_id, request_id)

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE,
            table_affected="time_corrections",
            record_id=correction_id,
            old_values=old_values,
            new_values=db_correction.__dict__,
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Time correction updated: correction_id={correction_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return TimeCorrectionOut.model_validate(db_correction)

    except TimeCorrectionNotFoundError as e:
        logger.error(f"Time correction not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error: {str(e)}", extra={"request_id": request_id})
        raise
    except DatabaseError as e:
        logger.error(f"Database error updating time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error updating time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def delete_time_correction(
    correction_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.DELETE_TIME_CORRECTION]))
) -> None:
    """
    Soft delete a time correction with logging."""
    try:
        query = select(TimeCorrections).where(
            TimeCorrections.correction_id == correction_id,
            TimeCorrections.is_active == True,
            TimeCorrections.deleted_at == None
        )
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
        old_values = db_correction.__dict__.copy()

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
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Time correction soft deleted: correction_id={correction_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except TimeCorrectionNotFoundError as e:
        logger.error(f"Time correction not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error: {str(e)}", extra={"request_id": request_id})
        raise
    except DatabaseError as e:
        logger.error(f"Database error deleting time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error deleting time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def _get_active_attendance(db: AsyncSession, attendance_id: int, request_id: Optional[str] = None) -> Optional[AttendanceRecords]:
    """
    Get active attendance record by ID.

    Args:
        db: Database session for performing queries.
        attendance_id: The ID of the attendance record to retrieve.
        request_id: Optional unique identifier for the request.

    Returns:
        Optional[AttendanceRecords]: The attendance record if found, else None.

    Raises:
        DatabaseError: If a database error occurs.
    """
    try:
        query = select(AttendanceRecords).where(
            AttendanceRecords.attendance_id == attendance_id,
            AttendanceRecords.is_active == True,
            AttendanceRecords.deleted_at == None
        )
        result = await db.execute(query)
        attendance = result.scalar_one_or_none()
        logger.debug(
            f"Retrieved attendance record: attendance_id={attendance_id}, found={bool(attendance)}",
            extra={"request_id": request_id}
        )
        return attendance
    except DatabaseError as e:
        logger.error(f"Database error retrieving attendance record {attendance_id}: {str(e)}", extra={"request_id": request_id})
        raise

async def _get_active_user(db: AsyncSession, user_id: int, request_id: Optional[str] = None) -> Optional[Users]:
    """
    Get active user by ID."""
    try:
        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        logger.debug(
            f"Retrieved user: user_id={user_id}, found={bool(user)}",
            extra={"request_id": request_id}
        )
        return user
    except DatabaseError as e:
        logger.error(f"Database error retrieving user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise

def _validate_correction_times(clock_in: Optional[datetime], clock_out: Optional[datetime]) -> None:
    """
    Validate that correction times are logical."""
    if clock_in and clock_out and clock_out <= clock_in:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Corrected clock-out time must be after corrected clock-in time"
        )

async def _notify_managers_of_correction(
    db: AsyncSession,
    user_id: int,
    correction: TimeCorrections,
    user: Users,
    request_id: Optional[str] = None
) -> None:
    """
    Send notification email to user's managers about new correction request."""
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
        logger.debug(
            f"Sent notifications to {len(hierarchies)} managers for correction_id={correction.correction_id}",
            extra={"request_id": request_id}
        )
    except Exception as e:
        logger.error(
            f"Failed to send manager notification for correction_id={correction.correction_id}: {str(e)}",
            extra={"request_id": request_id}
        )

async def _notify_user_of_status_change(
    db: AsyncSession,
    correction: TimeCorrections,
    correction_id: int,
    request_id: Optional[str] = None
) -> None:
    """
    Send notification to user when correction status changes."""
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
        logger.debug(
            f"Sent user notification for correction_id={correction_id}, status={correction.status.value}",
            extra={"request_id": request_id}
        )
    except Exception as e:
        logger.error(
            f"Failed to send user notification for correction_id={correction_id}: {str(e)}",
            extra={"request_id": request_id}
        )

async def _update_attendance_record(
    db: AsyncSession,
    correction: TimeCorrections,
    request_id: Optional[str] = None
) -> None:
    """
    Update attendance record with approved correction times."""
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
        logger.debug(
            f"Updated attendance record: attendance_id={correction.attendance_id}",
            extra={"request_id": request_id}
        )
    except AttendanceRecordNotFoundError as e:
        logger.error(f"Attendance record not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error updating attendance record {correction.attendance_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error updating attendance record {correction.attendance_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")