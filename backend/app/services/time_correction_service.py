from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.time_corrections import TimeCorrections
from app.models.attendance_records import AttendanceRecords
from app.models.users import Users
from app.models.employee_hierarchy import EmployeeHierarchy
from app.schemas.time_correction import TimeCorrectionCreate, TimeCorrectionOut, TimeCorrectionUpdate, TimeCorrectionApproval
from app.core.config import Settings, get_settings
from app.core.enums import Permission, SystemAction, CorrectionStatus
from app.core.mail import send_email, EmailSchema, get_user_email
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.exceptions import TimeCorrectionNotFoundError, AttendanceRecordNotFoundError, UserNotFoundError, ValidationError, DatabaseError, DepartmentNotFoundError
from app.services.system_log_service import create_system_log
from app.schemas.system_log import SystemLogCreate
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_user_exists, validate_attendance_record_exists
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
    """Create a new time correction request with validation, logging, and cache clearing."""
    try:
        # Validate attendance record and user
        await validate_attendance_record_exists(db, time_correction.attendance_id, request_id)
        await validate_user_exists(db, current_user.user_id, request_id)

        # Ensure user is creating correction for their own attendance
        attendance = await _get_active_attendance(db, time_correction.attendance_id, request_id)
        if attendance.user_id != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot create correction for another user")

        # Validate time correction logic
        _validate_correction_times(time_correction.corrected_clock_in, time_correction.corrected_clock_out)

        # Create time correction record
        db_time_correction = TimeCorrections(
            attendance_id=time_correction.attendance_id,
            user_id=current_user.user_id,
            original_clock_in=attendance.clock_in_time,
            original_clock_out=attendance.clock_out_time,
            corrected_clock_in=time_correction.corrected_clock_in,
            corrected_clock_out=time_correction.corrected_clock_out,
            reason=time_correction.reason,
            status=CorrectionStatus.UNDER_REVIEW,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        
        db.add(db_time_correction)
        await db.commit()
        await db.refresh(db_time_correction)

        # Invalidate cache
        await invalidate_cache_prefix("time_correction")
        await invalidate_cache_prefix(f"user:{current_user.user_id}")
        logger.debug(f"Cache cleared for time_correction and user:{current_user.user_id}")

        # Send notification to managers
        await _notify_managers_of_correction(db, current_user.user_id, db_time_correction, current_user, request_id)

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_TIME_CORRECTION,
            table_affected="time_corrections",
            record_id=db_time_correction.correction_id,
            old_values=None,
            new_values=db_time_correction.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Time correction created: correction_id={db_time_correction.correction_id}, user_id={current_user.user_id}",
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
    except HTTPException as e:
        logger.error(f"Authorization error: {str(e)}", extra={"request_id": request_id})
        raise
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
    """Retrieve a time correction by ID."""
    try:
        cache_key = f"time_correction:{correction_id}"
        cached_correction = await get_cache(cache_key)
        if cached_correction:
            return TimeCorrectionOut(**cached_correction)

        query = select(TimeCorrections).where(
            TimeCorrections.correction_id == correction_id,
            TimeCorrections.is_active == True,
            TimeCorrections.deleted_at == None
        )
        result = await db.execute(query)
        correction = result.scalar_one_or_none()

        if not correction:
            raise TimeCorrectionNotFoundError(correction_id=correction_id)

        correction_dict = TimeCorrectionOut.model_validate(correction).model_dump()
        await set_cache(cache_key, correction_dict, ttl=300)

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
    """Retrieve all time corrections for a specific user with pagination."""
    try:
        if skip < 0 or (limit is not None and limit < 0):
            raise ValidationError(detail="Invalid pagination parameters")

        await validate_user_exists(db, user_id, request_id)
        limit = limit or settings.DEFAULT_PAGE_SIZE

        cache_key = f"time_corrections:user:{user_id}:{skip}:{limit}"
        cached_corrections = await get_cache(cache_key)
        if cached_corrections:
            return [TimeCorrectionOut(**c) for c in cached_corrections]

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

        corrections_dict = [TimeCorrectionOut.model_validate(c).model_dump() for c in corrections]
        await set_cache(cache_key, corrections_dict, ttl=300)

        logger.info(
            f"Retrieved {len(corrections)} time corrections for user_id: {user_id}",
            extra={"request_id": request_id}
        )
        return [TimeCorrectionOut.model_validate(c) for c in corrections]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving time corrections for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving time corrections for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_department_time_corrections(
    department_id: int,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_TIME_CORRECTION]))
) -> List[TimeCorrectionOut]:
    """Retrieve all time corrections for a specific department with pagination."""
    try:
        if skip < 0 or (limit is not None and limit < 0):
            raise ValidationError(detail="Invalid pagination parameters")

        from app.models.user_departments import UserDepartments
        from app.core.validators import validate_department_exists
        await validate_department_exists(db, department_id, request_id)
        limit = limit or settings.DEFAULT_PAGE_SIZE

        cache_key = f"time_corrections:department:{department_id}:{skip}:{limit}"
        cached_corrections = await get_cache(cache_key)
        if cached_corrections:
            return [TimeCorrectionOut(**c) for c in cached_corrections]

        query = (
            select(TimeCorrections)
            .join(UserDepartments, UserDepartments.user_id == TimeCorrections.user_id)
            .where(
                UserDepartments.department_id == department_id,
                UserDepartments.is_active == True,
                UserDepartments.deleted_at == None,
                TimeCorrections.is_active == True,
                TimeCorrections.deleted_at == None
            )
            .order_by(TimeCorrections.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        
        result = await db.execute(query)
        corrections = result.scalars().all()

        corrections_dict = [TimeCorrectionOut.model_validate(c).model_dump() for c in corrections]
        await set_cache(cache_key, corrections_dict, ttl=300)

        logger.info(
            f"Retrieved {len(corrections)} time corrections for department_id: {department_id}",
            extra={"request_id": request_id}
        )
        return [TimeCorrectionOut.model_validate(c) for c in corrections]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DepartmentNotFoundError as e:
        logger.error(f"Department not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving time corrections for department_id {department_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving time corrections for department_id {department_id}: {str(e)}", extra={"request_id": request_id})
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
    """Update an existing time correction with validation, logging, and cache clearing."""
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

        # Check if user is authorized
        if db_correction.user_id != current_user.user_id:
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

        if "approved_by" in update_data and update_data["approved_by"]:
            await validate_user_exists(db, update_data["approved_by"], request_id)

        # Store old values for logging
        old_values = db_correction.__dict__.copy()

        # Apply updates
        for key, value in update_data.items():
            setattr(db_correction, key, value)

        db_correction.updated_at = datetime.now(timezone.utc)
        db.add(db_correction)
        await db.commit()
        await db.refresh(db_correction)

        # Invalidate cache
        await invalidate_cache_prefix("time_correction")
        await invalidate_cache_prefix(f"user:{db_correction.user_id}")
        logger.debug(f"Cache cleared for time_correction and user:{db_correction.user_id}")

        # Send status notification if status changed
        if "status" in update_data:
            await _notify_user_of_status_change(db, db_correction, correction_id, request_id)

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_TIME_CORRECTION,
            table_affected="time_corrections",
            record_id=correction_id,
            old_values=old_values,
            new_values=db_correction.__dict__,
            ip_address=str(request.client.host) if request else None,
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
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
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

async def approve_time_correction(
    correction_id: int,
    approval_data: TimeCorrectionApproval,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.UPDATE_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """Approve or reject a time correction with validation, logging, and cache clearing."""
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

        # Check if user is authorized
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
                detail="Not authorized to approve/reject this time correction"
            )

        # Store old values for logging
        old_values = db_correction.__dict__.copy()

        # Apply approval
        db_correction.status = approval_data.status
        db_correction.approved_by = current_user.user_id
        db_correction.approved_at = datetime.now(timezone.utc)
        db_correction.updated_at = datetime.now(timezone.utc)

        # Update attendance record if approved
        if approval_data.status == CorrectionStatus.APPROVED:
            await _update_attendance_record(db, db_correction, request_id)

        db.add(db_correction)
        await db.commit()
        await db.refresh(db_correction)

        # Invalidate cache
        await invalidate_cache_prefix("time_correction")
        await invalidate_cache_prefix(f"user:{db_correction.user_id}")
        logger.debug(f"Cache cleared for time_correction and user:{db_correction.user_id}")

        # Send status notification
        await _notify_user_of_status_change(db, db_correction, correction_id, request_id)

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_TIME_CORRECTION,
            table_affected="time_corrections",
            record_id=correction_id,
            old_values=old_values,
            new_values=db_correction.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Time correction {getattr(approval_data.status, 'value', approval_data.status)}: correction_id={correction_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return TimeCorrectionOut.model_validate(db_correction)

    except TimeCorrectionNotFoundError as e:
        logger.error(f"Time correction not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error: {str(e)}", extra={"request_id": request_id})
        raise
    except DatabaseError as e:
        logger.error(f"Database error approving time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error approving time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
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
    """Soft delete a time correction with logging and cache clearing."""
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
        db_correction.updated_at = datetime.now(timezone.utc)
        db.add(db_correction)
        await db.commit()

        # Invalidate cache
        await invalidate_cache_prefix("time_correction")
        await invalidate_cache_prefix(f"user:{db_correction.user_id}")
        logger.debug(f"Cache cleared for time_correction and user:{db_correction.user_id}")

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_TIME_CORRECTION,
            table_affected="time_corrections",
            record_id=correction_id,
            old_values=old_values,
            new_values=None,
            ip_address=str(request.client.host) if request else None,
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
    """Get active attendance record by ID."""
    try:
        query = select(AttendanceRecords).where(
            AttendanceRecords.attendance_id == attendance_id,
            AttendanceRecords.is_active == True,
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
    """Get active user by ID."""
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
    """Validate that correction times are logical."""
    if not clock_in and not clock_out:
        raise ValidationError(detail="At least one of corrected_clock_in or corrected_clock_out must be provided")
    if clock_in and clock_out and clock_out <= clock_in:
        raise ValidationError(detail="Corrected clock-out time must be after corrected clock-in time")

async def _notify_managers_of_correction(
    db: AsyncSession,
    user_id: int,
    correction: TimeCorrections,
    user: Users,
    request_id: Optional[str] = None
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
                        f"Status: {getattr(correction.status, 'value', correction.status)}\n\n"
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
    """Send notification to user when correction status changes."""
    try:
        user_email = await get_user_email(correction.user_id, db)
        # Handle both Enum and string statuses robustly
        status_value = getattr(correction.status, "value", correction.status)
        if user_email:
            status_text = str(status_value).replace('_', ' ').title()
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
            f"Sent user notification for correction_id={correction_id}, status={status_value}",
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
    """Update attendance record with approved correction times."""
    try:
        query = select(AttendanceRecords).where(
            AttendanceRecords.attendance_id == correction.attendance_id,
            AttendanceRecords.is_active == True
        )
        result = await db.execute(query)
        attendance = result.scalar_one_or_none()
        if not attendance:
            raise AttendanceRecordNotFoundError(attendance_id=correction.attendance_id)
        if correction.corrected_clock_in:
            attendance.clock_in_time = correction.corrected_clock_in
        if correction.corrected_clock_out:
            attendance.clock_out_time = correction.corrected_clock_out
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