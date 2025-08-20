from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select, and_
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from app.models.time_corrections import TimeCorrections
from app.models.attendance_records import AttendanceRecords
from app.models.users import Users
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.shift_assignments import ShiftAssignments
from app.models.shift_patterns import ShiftPatterns
from app.schemas.time_correction import TimeCorrectionCreate, TimeCorrectionOut, TimeCorrectionUpdate, TimeCorrectionApproval
from app.core.config import Settings, get_settings
from app.core.enums import Permission, SystemAction, CorrectionStatus
from app.core.mail import send_email
from app.core.security import get_current_user
from app.core.permissions import require_permissions, invalidate_user_cache, get_user_permissions
from app.core.exceptions import TimeCorrectionNotFoundError, AttendanceRecordNotFoundError, UserNotFoundError, ValidationError, DatabaseError, DepartmentNotFoundError
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_user_exists, validate_attendance_record_exists, validate_department_exists
from app.core.utils import get_request_id, get_users_with_permission
from app.services.system_log_service import create_system_log
from app.schemas.system_log import SystemLogCreate
from app.models.user_departments import UserDepartments
import logging

logger = logging.getLogger(__name__)

async def create_time_correction(
    time_correction: TimeCorrectionCreate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.CREATE_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """Create a new time correction request with validation, logging, and cache clearing."""
    try:
        if time_correction.attendance_id <= 0:
            raise ValidationError(detail="Invalid attendance_id")
        
        # Validate attendance record and user
        await validate_attendance_record_exists(db, time_correction.attendance_id, request_id)
        await validate_user_exists(db, current_user.user_id, request_id)

        # Ensure user is creating correction for their own attendance
        attendance = await _get_active_attendance(db, time_correction.attendance_id, request_id)
        if attendance.user_id != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot create correction for another user")

        # Validate time correction against shift assignments
        await _validate_correction_against_shift(db, time_correction, current_user.user_id, request_id, settings)

        # Validate time correction logic
        _validate_correction_times(time_correction.corrected_clock_in, time_correction.corrected_clock_out, settings)

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
        invalidate_user_cache(current_user.user_id)
        await invalidate_cache_prefix("time_correction")
        await invalidate_cache_prefix(f"user:{current_user.user_id}")
        logger.info(f"Cache invalidated for time_correction and user:{current_user.user_id}", extra={"request_id": request_id})

        # Send notification to managers and admins
        await _notify_managers_and_admins_of_correction(db, current_user.user_id, db_time_correction, current_user, request_id, settings)

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
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Time correction created: correction_id={db_time_correction.correction_id}, user_id={current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return TimeCorrectionOut.model_validate(db_time_correction)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (AttendanceRecordNotFoundError, UserNotFoundError) as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
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
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """Retrieve a time correction by ID with authorization check."""
    try:
        if correction_id <= 0:
            raise ValidationError(detail="Invalid correction_id")

        cache_key = f"time_correction:{correction_id}"
        cached_correction = await get_cache(cache_key)
        if cached_correction:
            logger.info(f"Cache hit for time_correction:{correction_id}", extra={"request_id": request_id})
            return TimeCorrectionOut(**cached_correction)

        query = select(TimeCorrections).where(
            TimeCorrections.correction_id == correction_id,
            TimeCorrections.is_active.is_(True),
            TimeCorrections.deleted_at.is_(None)
        )
        result = await db.execute(query)
        correction = result.scalar_one_or_none()

        if not correction:
            raise TimeCorrectionNotFoundError(correction_id=correction_id)

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if correction.user_id != current_user.user_id:
            query_hierarchy = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == correction.user_id,
                EmployeeHierarchy.supervisor_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result_hierarchy = await db.execute(query_hierarchy)
            if not result_hierarchy.scalar_one_or_none() and not any(p == Permission.VIEW_TIME_CORRECTION.value or p == Permission.MANAGE_TIME_CORRECTION.value for p in user_permissions):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view this time correction"
                )

        correction_dict = TimeCorrectionOut.model_validate(correction).model_dump()
        await set_cache(cache_key, correction_dict, ttl=300)
        logger.info(f"Cache set for time_correction:{correction_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved time correction: correction_id={correction_id}, user_id={current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return TimeCorrectionOut.model_validate(correction)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except TimeCorrectionNotFoundError as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error retrieving time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
        raise
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
    status: Optional[CorrectionStatus] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_TIME_CORRECTION]))
) -> List[TimeCorrectionOut]:
    """Retrieve all time corrections for a specific user with pagination and optional status filter."""
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user_id")
        if skip < 0 or (limit is not None and limit < 0):
            raise ValidationError(detail="Invalid pagination parameters")

        await validate_user_exists(db, user_id, request_id)
        limit = limit or settings.DEFAULT_PAGE_SIZE

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if user_id != current_user.user_id:
            query_hierarchy = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == user_id,
                EmployeeHierarchy.supervisor_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result_hierarchy = await db.execute(query_hierarchy)
            if not result_hierarchy.scalar_one_or_none() and not any(p == Permission.VIEW_TIME_CORRECTION.value or p == Permission.MANAGE_TIME_CORRECTION.value for p in user_permissions):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view time corrections for this user"
                )

        cache_key = f"time_corrections:user:{user_id}:{skip}:{limit}:{status or 'all'}"
        cached_corrections = await get_cache(cache_key)
        if cached_corrections:
            logger.info(f"Cache hit for time_corrections:user:{user_id}:{skip}:{limit}:{status or 'all'}", extra={"request_id": request_id})
            return [TimeCorrectionOut(**c) for c in cached_corrections]

        query = select(TimeCorrections).where(
            TimeCorrections.user_id == user_id,
            TimeCorrections.is_active.is_(True),
            TimeCorrections.deleted_at.is_(None)
        )
        if status:
            query = query.where(TimeCorrections.status == status)
        query = query.order_by(TimeCorrections.correction_id.asc()).offset(skip).limit(limit)
        
        result = await db.execute(query)
        corrections = result.scalars().all()

        corrections_dict = [TimeCorrectionOut.model_validate(c).model_dump() for c in corrections]
        await set_cache(cache_key, corrections_dict, ttl=300)
        logger.info(f"Cache set for time_corrections:user:{user_id}:{skip}:{limit}:{status or 'all'}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(corrections)} time corrections for user_id: {user_id}, status: {status or 'all'}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [TimeCorrectionOut.model_validate(c) for c in corrections]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error retrieving time corrections for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise
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
    status: Optional[CorrectionStatus] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_TIME_CORRECTION]))
) -> List[TimeCorrectionOut]:
    """Retrieve all time corrections for a specific department with pagination and optional status filter."""
    try:
        if department_id <= 0:
            raise ValidationError(detail="Invalid department_id")
        if skip < 0 or (limit is not None and limit < 0):
            raise ValidationError(detail="Invalid pagination parameters")

        await validate_department_exists(db, department_id, request_id)
        limit = limit or settings.DEFAULT_PAGE_SIZE

        cache_key = f"time_corrections:department:{department_id}:{skip}:{limit}:{status or 'all'}"
        cached_corrections = await get_cache(cache_key)
        if cached_corrections:
            logger.info(f"Cache hit for time_corrections:department:{department_id}:{skip}:{limit}:{status or 'all'}", extra={"request_id": request_id})
            return [TimeCorrectionOut(**c) for c in cached_corrections]

        query = select(TimeCorrections).join(
            UserDepartments, 
            and_(
                UserDepartments.user_id == TimeCorrections.user_id,
                UserDepartments.department_id == department_id,
                UserDepartments.is_active.is_(True),
                UserDepartments.deleted_at.is_(None)
            )
        ).where(
            TimeCorrections.is_active.is_(True),
            TimeCorrections.deleted_at.is_(None)
        )
        if status:
            query = query.where(TimeCorrections.status == status)
        query = query.order_by(TimeCorrections.correction_id.asc()).offset(skip).limit(limit)
        
        result = await db.execute(query)
        corrections = result.scalars().all()

        corrections_dict = [TimeCorrectionOut.model_validate(c).model_dump() for c in corrections]
        await set_cache(cache_key, corrections_dict, ttl=300)
        logger.info(f"Cache set for time_corrections:department:{department_id}:{skip}:{limit}:{status or 'all'}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(corrections)} time corrections for department_id: {department_id}, status: {status or 'all'}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [TimeCorrectionOut.model_validate(c) for c in corrections]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DepartmentNotFoundError as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error retrieving time corrections for department_id {department_id}: {str(e)}", extra={"request_id": request_id})
        raise
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
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.UPDATE_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """Update an existing time correction with validation, logging, and cache clearing."""
    try:
        if correction_id <= 0:
            raise ValidationError(detail="Invalid correction_id")

        # Get existing time correction
        query = select(TimeCorrections).where(
            TimeCorrections.correction_id == correction_id,
            TimeCorrections.is_active.is_(True),
            TimeCorrections.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_correction = result.scalar_one_or_none()

        if not db_correction:
            raise TimeCorrectionNotFoundError(correction_id=correction_id)

        # Check if correction is in a final state
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if db_correction.status in [CorrectionStatus.APPROVED, CorrectionStatus.REJECTED] and not any(p == Permission.MANAGE_TIME_CORRECTION.value for p in user_permissions):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot update approved or rejected time correction")

        # Authorization check
        if db_correction.user_id != current_user.user_id:
            query_hierarchy = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == db_correction.user_id,
                EmployeeHierarchy.supervisor_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result_hierarchy = await db.execute(query_hierarchy)
            if not result_hierarchy.scalar_one_or_none() and not any(p == Permission.MANAGE_TIME_CORRECTION.value for p in user_permissions):
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
        _validate_correction_times(corrected_clock_in, corrected_clock_out, settings)

        # Validate against shift assignments if times are updated
        if "corrected_clock_in" in update_data or "corrected_clock_out" in update_data:
            await _validate_correction_against_shift(db, TimeCorrectionCreate(
                attendance_id=db_correction.attendance_id,
                corrected_clock_in=corrected_clock_in,
                corrected_clock_out=corrected_clock_out,
                reason=update_data.get("reason", db_correction.reason)
            ), db_correction.user_id, request_id, settings)

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
        invalidate_user_cache(db_correction.user_id)
        await invalidate_cache_prefix("time_correction")
        await invalidate_cache_prefix(f"user:{db_correction.user_id}")
        logger.info(f"Cache invalidated for time_correction and user:{db_correction.user_id}", extra={"request_id": request_id})

        # Send status notification if status changed
        if "status" in update_data:
            await _notify_user_and_admins_of_status_change(db, db_correction, correction_id, current_user, request_id, settings)

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
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Time correction updated: correction_id={correction_id}, user_id={current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return TimeCorrectionOut.model_validate(db_correction)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (TimeCorrectionNotFoundError, UserNotFoundError) as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization or conflict error updating time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
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
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.UPDATE_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """Approve or reject a time correction with validation, logging, and cache clearing."""
    try:
        if correction_id <= 0:
            raise ValidationError(detail="Invalid correction_id")
        if approval_data.status not in CorrectionStatus:
            raise ValidationError(detail=f"Invalid status: {approval_data.status}")

        # Get existing time correction
        query = select(TimeCorrections).where(
            TimeCorrections.correction_id == correction_id,
            TimeCorrections.is_active.is_(True),
            TimeCorrections.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_correction = result.scalar_one_or_none()

        if not db_correction:
            raise TimeCorrectionNotFoundError(correction_id=correction_id)

        # Check if correction is already in a final state
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if db_correction.status in [CorrectionStatus.APPROVED, CorrectionStatus.REJECTED] and not any(p == Permission.MANAGE_TIME_CORRECTION.value for p in user_permissions):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Time correction is already approved or rejected")

        # Authorization check
        query_hierarchy = select(EmployeeHierarchy).where(
            EmployeeHierarchy.employee_id == db_correction.user_id,
            EmployeeHierarchy.supervisor_id == current_user.user_id,
            EmployeeHierarchy.is_active.is_(True),
            EmployeeHierarchy.deleted_at.is_(None)
        )
        result_hierarchy = await db.execute(query_hierarchy)
        if not result_hierarchy.scalar_one_or_none() and not any(p == Permission.MANAGE_TIME_CORRECTION.value for p in user_permissions):
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
        invalidate_user_cache(db_correction.user_id)
        await invalidate_cache_prefix("time_correction")
        await invalidate_cache_prefix(f"user:{db_correction.user_id}")
        logger.info(f"Cache invalidated for time_correction and user:{db_correction.user_id}", extra={"request_id": request_id})

        # Send status notification
        await _notify_user_and_admins_of_status_change(db, db_correction, correction_id, current_user, request_id, settings)

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
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Time correction {approval_data.status.value}: correction_id={correction_id}, user_id={current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return TimeCorrectionOut.model_validate(db_correction)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except TimeCorrectionNotFoundError as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization or conflict error approving time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
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
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.DELETE_TIME_CORRECTION]))
) -> None:
    """Soft delete a time correction with logging and cache clearing."""
    try:
        if correction_id <= 0:
            raise ValidationError(detail="Invalid correction_id")

        query = select(TimeCorrections).where(
            TimeCorrections.correction_id == correction_id,
            TimeCorrections.is_active.is_(True),
            TimeCorrections.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_correction = result.scalar_one_or_none()

        if not db_correction:
            raise TimeCorrectionNotFoundError(correction_id=correction_id)

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if not any(p == Permission.MANAGE_TIME_CORRECTION.value for p in user_permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only HR or admins can delete time corrections"
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
        invalidate_user_cache(db_correction.user_id)
        await invalidate_cache_prefix("time_correction")
        await invalidate_cache_prefix(f"user:{db_correction.user_id}")
        logger.info(f"Cache invalidated for time_correction and user:{db_correction.user_id}", extra={"request_id": request_id})

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
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Time correction soft deleted: correction_id={correction_id}, user_id={current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except TimeCorrectionNotFoundError as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error deleting time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
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
            AttendanceRecords.is_active.is_(True)
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
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
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

def _validate_correction_times(clock_in: Optional[datetime], clock_out: Optional[datetime], settings: Settings) -> None:
    """Validate that correction times are logical and within constraints."""
    if not clock_in and not clock_out:
        raise ValidationError(detail="At least one of corrected_clock_in or corrected_clock_out must be provided")
    if clock_in and clock_out and clock_out <= clock_in:
        raise ValidationError(detail="Corrected clock-out time must be after corrected clock-in time")
    if clock_in and clock_out:
        time_diff = (clock_out - clock_in).total_seconds() / 3600
        if time_diff > settings.MAX_TIME_CORRECTION_HOURS:
            raise ValidationError(detail=f"Time correction exceeds maximum allowed hours ({settings.MAX_TIME_CORRECTION_HOURS})")

async def _validate_correction_against_shift(
    db: AsyncSession,
    time_correction: TimeCorrectionCreate,
    user_id: int,
    request_id: Optional[str],
    settings: Settings
) -> None:
    """Validate corrected times against user's assigned shift."""
    try:
        query_attendance = select(AttendanceRecords).where(
            AttendanceRecords.attendance_id == time_correction.attendance_id,
            AttendanceRecords.is_active.is_(True)
        )
        result_attendance = await db.execute(query_attendance)
        attendance = result_attendance.scalar_one_or_none()
        if not attendance:
            raise AttendanceRecordNotFoundError(attendance_id=time_correction.attendance_id)

        query_shift = select(ShiftAssignments).join(
            ShiftPatterns,
            and_(
                ShiftPatterns.pattern_id == ShiftAssignments.pattern_id,
                ShiftPatterns.is_active.is_(True),
                ShiftPatterns.deleted_at.is_(None)
            )
        ).where(
            ShiftAssignments.user_id == user_id,
            ShiftAssignments.is_active.is_(True),
            ShiftAssignments.deleted_at.is_(None),
            ShiftAssignments.start_date <= attendance.attendance_date,
            or_(ShiftAssignments.end_date.is_(None), ShiftAssignments.end_date >= attendance.attendance_date)
        )
        result_shift = await db.execute(query_shift)
        shift = result_shift.scalar_one_or_none()

        if shift and settings.PREVENT_INVALID_TIME_CORRECTIONS:
            shift_pattern = shift.pattern
            shift_start = datetime.combine(attendance.attendance_date, shift_pattern.start_time)
            shift_end = datetime.combine(attendance.attendance_date, shift_pattern.end_time)
            if shift_pattern.end_time < shift_pattern.start_time:  # Handle overnight shifts
                shift_end += timedelta(days=1)
            
            if time_correction.corrected_clock_in and time_correction.corrected_clock_in < shift_start - timedelta(minutes=30):
                raise ValidationError(detail="Corrected clock-in time is too early for assigned shift")
            if time_correction.corrected_clock_out and time_correction.corrected_clock_out > shift_end + timedelta(minutes=30):
                raise ValidationError(detail="Corrected clock-out time is too late for assigned shift")
        
        logger.debug(
            f"Validated correction times against shift for attendance_id={time_correction.attendance_id}, user_id={user_id}",
            extra={"request_id": request_id}
        )
    except ValidationError as e:
        raise
    except DatabaseError as e:
        logger.error(f"Database error validating shift for attendance_id {time_correction.attendance_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error validating shift for attendance_id {time_correction.attendance_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error validating shift")

async def _notify_managers_and_admins_of_correction(
    db: AsyncSession,
    user_id: int,
    correction: TimeCorrections,
    user: Users,
    request_id: Optional[str],
    settings: Settings
) -> None:
    """Send notification email to user's managers and admins about new correction request."""
    try:
        eat_tz = ZoneInfo("Africa/Nairobi")
        current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
        recipients = []
        
        # Get managers
        query_hierarchy = select(EmployeeHierarchy).where(
            EmployeeHierarchy.employee_id == user_id,
            EmployeeHierarchy.is_active.is_(True),
            EmployeeHierarchy.deleted_at.is_(None)
        )
        result_hierarchy = await db.execute(query_hierarchy)
        hierarchies = result_hierarchy.scalars().all()
        for hierarchy in hierarchies:
            manager = await _get_active_user(db, hierarchy.supervisor_id, request_id)
            if manager and manager.email:
                recipients.append((manager.email, manager.first_name))

        # Get admins
        admins = await get_users_with_permission(Permission.MANAGE_TIME_CORRECTION, db)
        recipients.extend([(admin.email, admin.first_name) for admin in admins if admin.email])

        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"New Time Correction Request (ID: {correction.correction_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"A new time correction request has been submitted by {user.first_name} {user.last_name} ({user.email}).\n\n"
                    f"Details:\n"
                    f"Correction ID: {correction.correction_id}\n"
                    f"Attendance ID: {correction.attendance_id}\n"
                    f"Original Clock-In: {correction.original_clock_in}\n"
                    f"Original Clock-Out: {correction.original_clock_out}\n"
                    f"Corrected Clock-In: {correction.corrected_clock_in}\n"
                    f"Corrected Clock-Out: {correction.corrected_clock_out}\n"
                    f"Reason: {correction.reason}\n"
                    f"Status: {correction.status.value}\n"
                    f"Submitted At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )
        logger.info(
            f"Sent notifications to {len(recipients)} recipients for correction_id={correction.correction_id}",
            extra={"request_id": request_id}
        )
    except Exception as e:
        logger.error(
            f"Failed to send notifications for correction_id={correction.correction_id}: {str(e)}",
            extra={"request_id": request_id}
        )

async def _notify_user_and_admins_of_status_change(
    db: AsyncSession,
    correction: TimeCorrections,
    correction_id: int,
    current_user: Users,
    request_id: Optional[str],
    settings: Settings
) -> None:
    """Send notification to user and admins when correction status changes."""
    try:
        eat_tz = ZoneInfo("Africa/Nairobi")
        current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
        recipients = []
        
        # Notify user
        user = await _get_active_user(db, correction.user_id, request_id)
        if user and user.email:
            recipients.append((user.email, user.first_name))
        
        # Notify admins
        admins = await get_users_with_permission(Permission.MANAGE_TIME_CORRECTION, db)
        recipients.extend([(admin.email, admin.first_name) for admin in admins if admin.email])

        status_value = correction.status.value
        status_text = status_value.replace('_', ' ').title()
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"Time Correction {status_text} (ID: {correction_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"The time correction request (ID: {correction_id}) has been {status_text.lower()}.\n\n"
                    f"Details:\n"
                    f"Attendance ID: {correction.attendance_id}\n"
                    f"Corrected Clock-In: {correction.corrected_clock_in}\n"
                    f"Corrected Clock-Out: {correction.corrected_clock_out}\n"
                    f"Reason: {correction.reason}\n"
                    f"Status: {status_text}\n"
                    f"Updated At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )
        logger.info(
            f"Sent status change notifications to {len(recipients)} recipients for correction_id={correction_id}, status={status_value}",
            extra={"request_id": request_id}
        )
    except Exception as e:
        logger.error(
            f"Failed to send status change notifications for correction_id={correction_id}: {str(e)}",
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
            AttendanceRecords.is_active.is_(True)
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
        logger.info(
            f"Updated attendance record: attendance_id={correction.attendance_id}",
            extra={"request_id": request_id}
        )
    except AttendanceRecordNotFoundError as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error updating attendance record {correction.attendance_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error updating attendance record {correction.attendance_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")