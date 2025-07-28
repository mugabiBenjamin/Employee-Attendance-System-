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
from app.core.exceptions import UserNotFoundError
import logging
from app.schemas.time_correction import TimeCorrectionCreate, TimeCorrectionOut, TimeCorrectionUpdate

logger = logging.getLogger(__name__)

async def create_time_correction(db: AsyncSession, time_correction: TimeCorrectionCreate, current_user: Users) -> TimeCorrectionOut:
    """
    Create a new time correction with validation, logging, and email notification to manager.
    """
    try:
        # Validate attendance record
        query = select(AttendanceRecords).where(
            AttendanceRecords.attendance_id == time_correction.attendance_id,
            AttendanceRecords.is_active == True,
            AttendanceRecords.deleted_at == None
        )
        result = await db.execute(query)
        attendance = result.scalar_one_or_none()
        if not attendance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attendance record not found"
            )

        # Validate user
        query = select(Users).where(
            Users.user_id == time_correction.user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            raise UserNotFoundError(detail="User not found")

        # Validate time logic
        if time_correction.corrected_clock_in and time_correction.corrected_clock_out:
            if time_correction.corrected_clock_out <= time_correction.corrected_clock_in:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Corrected clock-out time must be after corrected clock-in time"
                )

        # Create time correction
        db_time_correction = TimeCorrections(
            attendance_id=time_correction.attendance_id,
            user_id=time_correction.user_id,
            original_clock_in=time_correction.original_clock_in,
            original_clock_out=time_correction.original_clock_out,
            corrected_clock_in=time_correction.corrected_clock_in,
            corrected_clock_out=time_correction.corrected_clock_out,
            reason=time_correction.reason,
            status=time_correction.status,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_time_correction)
        await db.commit()
        await db.refresh(db_time_correction)

        # Send notification to manager
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.employee_id == time_correction.user_id,
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
        result = await db.execute(query)
        hierarchy = result.scalars().all()

        for h in hierarchy:
            manager_email = await get_user_email(h.manager_id, db)
            if manager_email:
                email_data = EmailSchema(
                    to_email=manager_email,
                    subject=f"New Time Correction Request (ID: {db_time_correction.correction_id})",
                    body=(
                        f"A new time correction request has been submitted.\n\n"
                        f"User: {user.email}\n"
                        f"Attendance ID: {time_correction.attendance_id}\n"
                        f"Reason: {time_correction.reason}\n"
                        f"Status: {time_correction.status.value}\n"
                    )
                )
                await send_email(email_data)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="time_corrections",
            record_id=db_time_correction.correction_id,
            old_values=None,
            new_values=db_time_correction.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Time correction created, correction_id: {db_time_correction.correction_id}, user_id: {time_correction.user_id}")
        return TimeCorrectionOut.model_validate(db_time_correction)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating time correction for user_id {time_correction.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating time correction"
        )

async def get_time_correction_by_id(db: AsyncSession, correction_id: int) -> Optional[TimeCorrectionOut]:
    """
    Retrieve a time correction by ID.
    """
    try:
        query = select(TimeCorrections).where(
            TimeCorrections.correction_id == correction_id,
            TimeCorrections.is_active == True,
            TimeCorrections.deleted_at == None
        )
        result = await db.execute(query)
        correction = result.scalar_one_or_none()

        if not correction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Time correction not found"
            )

        return TimeCorrectionOut.model_validate(correction)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving time correction {correction_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving time correction"
        )

async def get_user_time_corrections(db: AsyncSession, user_id: int, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[TimeCorrectionOut]:
    """
    Retrieve a list of time corrections for a user with pagination.
    """
    try:
        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise UserNotFoundError(detail="User not found")

        query = select(TimeCorrections).where(
            TimeCorrections.user_id == user_id,
            TimeCorrections.is_active == True,
            TimeCorrections.deleted_at == None
        ).offset(skip).limit(limit)
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
            detail="Error retrieving time corrections"
        )

async def update_time_correction(db: AsyncSession, correction_id: int, time_correction_update: TimeCorrectionUpdate, current_user: Users) -> TimeCorrectionOut:
    """
    Update a time correction with validation, logging, and email notification.
    """
    try:
        # Retrieve time correction
        query = select(TimeCorrections).where(
            TimeCorrections.correction_id == correction_id,
            TimeCorrections.is_active == True,
            TimeCorrections.deleted_at == None
        )
        result = await db.execute(query)
        db_correction = result.scalar_one_or_none()

        if not db_correction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Time correction not found"
            )

        # Validate time logic if updated
        update_data = time_correction_update.model_dump(exclude_none=True)
        corrected_clock_in = update_data.get("corrected_clock_in", db_correction.corrected_clock_in)
        corrected_clock_out = update_data.get("corrected_clock_out", db_correction.corrected_clock_out)
        if corrected_clock_in and corrected_clock_out and corrected_clock_out <= corrected_clock_in:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Corrected clock-out time must be after corrected clock-in time"
            )

        # Store old values for logging
        old_values = db_correction.__dict__.copy()

        # Apply updates
        for key, value in update_data.items():
            setattr(db_correction, key, value)

        # Handle approval if status is updated to APPROVED
        if "status" in update_data and update_data["status"] == CorrectionStatus.APPROVED:
            db_correction.approved_by = current_user.user_id
            db_correction.approved_at = datetime.now(timezone.utc)

        db_correction.updated_at = datetime.now(timezone.utc)
        db.add(db_correction)
        await db.commit()
        await db.refresh(db_correction)

        # Send notification to user if status changed
        if "status" in update_data:
            user_email = await get_user_email(db_correction.user_id, db)
            if user_email:
                status_action = "approved" if update_data["status"] == CorrectionStatus.APPROVED else "rejected"
                email_data = EmailSchema(
                    to_email=user_email,
                    subject=f"Time Correction {status_action.capitalize()} (ID: {correction_id})",
                    body=(
                        f"Dear User,\n\n"
                        f"Your time correction request (ID: {correction_id}) has been {status_action}.\n"
                        f"Reason: {db_correction.reason}\n"
                        f"Status: {db_correction.status.value}\n\n"
                        f"Please contact HR for any questions.\n\n"
                        f"Best regards,\nEmployee Management System"
                    )
                )
                await send_email(email_data)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE,
            table_affected="time_corrections",
            record_id=correction_id,
            old_values=old_values,
            new_values=db_correction.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Time correction updated, correction_id: {correction_id}")
        return TimeCorrectionOut.model_validate(db_correction)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating time correction {correction_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating time correction"
        )

async def delete_time_correction(db: AsyncSession, correction_id: int, current_user: Users) -> None:
    """
    Soft delete a time correction with logging.
    """
    try:
        query = select(TimeCorrections).where(
            TimeCorrections.correction_id == correction_id,
            TimeCorrections.is_active == True,
            TimeCorrections.deleted_at == None
        )
        result = await db.execute(query)
        db_correction = result.scalar_one_or_none()

        if not db_correction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Time correction not found"
            )

        db_correction.is_active = False
        db_correction.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.DELETE,
            table_affected="time_corrections",
            record_id=correction_id,
            old_values=db_correction.__dict__,
            new_values=None,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Time correction soft deleted, correction_id: {correction_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting time correction {correction_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting time correction"
        )