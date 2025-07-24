from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.time_corrections import TimeCorrections
from app.models.attendance_records import AttendanceRecords
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.core.config import settings
from app.core.enums import SystemAction, CorrectionStatus
from app.core.mail import send_email_notification
import logging

logger = logging.getLogger(__name__)

class TimeCorrectionCreateInternal(BaseModel):
    attendance_id: int
    user_id: int
    original_clock_in: Optional[datetime] = None
    original_clock_out: Optional[datetime] = None
    corrected_clock_in: Optional[datetime] = None
    corrected_clock_out: Optional[datetime] = None
    reason: str
    status: CorrectionStatus = CorrectionStatus.DRAFT

    model_config = ConfigDict(from_attributes=True)

class TimeCorrectionUpdateInternal(BaseModel):
    corrected_clock_in: Optional[datetime] = None
    corrected_clock_out: Optional[datetime] = None
    reason: Optional[str] = None
    status: Optional[CorrectionStatus] = None

    model_config = ConfigDict(from_attributes=True)

class TimeCorrectionOut(BaseModel):
    correction_id: int
    attendance_id: int
    user_id: int
    original_clock_in: Optional[datetime]
    original_clock_out: Optional[datetime]
    corrected_clock_in: Optional[datetime]
    corrected_clock_out: Optional[datetime]
    reason: str
    status: CorrectionStatus
    approved_by: Optional[int]
    approved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

async def create_time_correction(db: AsyncSession, correction: TimeCorrectionCreateInternal, current_user: Users) -> TimeCorrectionOut:
    """
    Create a new time correction request with validation, logging, and email notification.
    """
    try:
        # Validate attendance record
        query = select(AttendanceRecords).where(
            AttendanceRecords.attendance_id == correction.attendance_id,
            AttendanceRecords.user_id == current_user.user_id,
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

        # Validate correction times
        if correction.corrected_clock_out and correction.corrected_clock_in and correction.corrected_clock_out <= correction.corrected_clock_in:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Corrected clock-out time must be after corrected clock-in time"
            )

        # Create time correction
        db_correction = TimeCorrections(
            **correction.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_correction)
        await db.commit()
        await db.refresh(db_correction)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.TIME_CORRECTION_SUBMITTED,
            table_affected="time_corrections",
            record_id=db_correction.correction_id,
            old_values=None,
            new_values=db_correction.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        # Send email notification to manager
        query = select(Users).join(
            EmployeeHierarchy,
            EmployeeHierarchy.manager_id == Users.user_id
        ).where(
            EmployeeHierarchy.employee_id == current_user.user_id,
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
        result = await db.execute(query)
        manager = result.scalar_one_or_none()
        if manager:
            await send_email_notification(
                to_email=manager.email,
                subject="New Time Correction Request Submitted",
                body=f"Employee {current_user.first_name} {current_user.last_name} submitted a time correction request for attendance ID {correction.attendance_id}."
            )

        logger.info(f"Time correction created, correction_id: {db_correction.correction_id}, user_id: {current_user.user_id}")
        return TimeCorrectionOut.model_validate(db_correction)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating time correction for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating time correction"
        )

async def get_time_correction_by_id(db: AsyncSession, correction_id: int, current_user: Users) -> Optional[TimeCorrectionOut]:
    """
    Retrieve a time correction request by ID for the current user.
    """
    try:
        query = select(TimeCorrections).where(
            TimeCorrections.correction_id == correction_id,
            TimeCorrections.user_id == current_user.user_id,
            TimeCorrections.is_active == True,
            TimeCorrections.deleted_at == None
        )
        result = await db.execute(query)
        correction = result.scalar_one_or_none()

        if not correction:
            return None

        logger.info(f"Retrieved time correction, correction_id: {correction_id}, user_id: {current_user.user_id}")
        return TimeCorrectionOut.model_validate(correction)

    except Exception as e:
        logger.error(f"Error retrieving time correction {correction_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving time correction"
        )

async def get_user_time_corrections(db: AsyncSession, current_user: Users, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[TimeCorrectionOut]:
    """
    Retrieve a list of time correction requests for the current user with pagination.
    """
    try:
        query = select(TimeCorrections).where(
            TimeCorrections.user_id == current_user.user_id,
            TimeCorrections.is_active == True,
            TimeCorrections.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        corrections = result.scalars().all()

        logger.info(f"Retrieved {len(corrections)} time corrections for user_id: {current_user.user_id}")
        return [TimeCorrectionOut.model_validate(correction) for correction in corrections]

    except Exception as e:
        logger.error(f"Error retrieving time corrections for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving time corrections"
        )

async def update_time_correction(db: AsyncSession, correction_id: int, correction_update: TimeCorrectionUpdateInternal, current_user: Users) -> TimeCorrectionOut:
    """
    Update a time correction request with validation, logging, and email notification.
    """
    try:
        # Retrieve correction
        query = select(TimeCorrections).where(
            TimeCorrections.correction_id == correction_id,
            TimeCorrections.user_id == current_user.user_id,
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

        # Validate status transition
        if correction_update.status and correction_update.status != db_correction.status:
            valid_transitions = {
                CorrectionStatus.DRAFT: [CorrectionStatus.UNDER_REVIEW, CorrectionStatus.CANCELLED],
                CorrectionStatus.UNDER_REVIEW: [CorrectionStatus.APPROVED, CorrectionStatus.REJECTED, CorrectionStatus.CANCELLED],
                CorrectionStatus.APPROVED: [CorrectionStatus.COMPLETED],
                CorrectionStatus.REJECTED: [],
                CorrectionStatus.CANCELLED: [],
                CorrectionStatus.COMPLETED: []
            }
            if correction_update.status not in valid_transitions[db_correction.status]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status transition from {db_correction.status} to {correction_update.status}"
                )

        # Validate correction times if updated
        update_data = correction_update.model_dump(exclude_none=True)
        if "corrected_clock_in" in update_data or "corrected_clock_out" in update_data:
            new_clock_in = update_data.get("corrected_clock_in", db_correction.corrected_clock_in)
            new_clock_out = update_data.get("corrected_clock_out", db_correction.corrected_clock_out)
            if new_clock_out and new_clock_in and new_clock_out <= new_clock_in:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Corrected clock-out time must be after corrected clock-in time"
                )

        # Store old values for logging
        old_values = db_correction.__dict__.copy()

        # Apply updates
        for key, value in update_data.items():
            setattr(db_correction, key, value)

        db_correction.updated_at = datetime.now(timezone.utc)
        if correction_update.status in [CorrectionStatus.APPROVED, CorrectionStatus.REJECTED]:
            db_correction.approved_by = current_user.user_id
            db_correction.approved_at = datetime.now(timezone.utc)

        db.add(db_correction)
        await db.commit()
        await db.refresh(db_correction)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.TIME_CORRECTION_UPDATED,
            table_affected="time_corrections",
            record_id=correction_id,
            old_values=old_values,
            new_values=db_correction.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        # Send email notification to manager if status changed
        if correction_update.status and correction_update.status != old_values["status"]:
            query = select(Users).join(
                EmployeeHierarchy,
                EmployeeHierarchy.manager_id == Users.user_id
            ).where(
                EmployeeHierarchy.employee_id == current_user.user_id,
                EmployeeHierarchy.is_active == True,
                EmployeeHierarchy.deleted_at == None
            )
            result = await db.execute(query)
            manager = result.scalar_one_or_none()
            if manager:
                await send_email_notification(
                    to_email=manager.email,
                    subject=f"Time Correction Request {correction_update.status.value.capitalize()}",
                    body=f"Employee {current_user.first_name} {current_user.last_name}'s time correction request (ID: {correction_id}) has been {correction_update.status.value}."
                )

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
    Soft delete a time correction request with logging.
    """
    try:
        query = select(TimeCorrections).where(
            TimeCorrections.correction_id == correction_id,
            TimeCorrections.user_id == current_user.user_id,
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
            action=SystemAction.TIME_CORRECTION_DELETED,
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