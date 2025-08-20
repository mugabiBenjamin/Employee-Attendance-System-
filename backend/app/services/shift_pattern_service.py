from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, timezone
from app.models.shift_patterns import ShiftPatterns
from app.models.users import Users
from app.models.shift_assignments import ShiftAssignments
from app.models.user_departments import UserDepartments
from app.schemas.shift_pattern import ShiftPatternCreate, ShiftPatternUpdate, ShiftPatternOut
from app.schemas.system_log import SystemLogCreate
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission, ShiftType
from app.core.exceptions import ShiftPatternNotFoundError, ValidationError, DatabaseError
from app.core.security import get_current_user
from app.core.permissions import require_permissions, invalidate_user_cache, get_user_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_shift_pattern_exists
from app.core.utils import get_request_id, get_users_with_permission
from app.services.system_log_service import create_system_log
from app.core.mail import send_email
import logging

logger = logging.getLogger(__name__)

async def create_shift_pattern(
    shift_pattern: ShiftPatternCreate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.CREATE_SHIFT_PATTERN]))
) -> ShiftPatternOut:
    """Create a new shift pattern with validation, logging, and notification."""
    try:
        # Validate inputs
        if shift_pattern.break_duration < 0:
            raise ValidationError(detail="Break duration must be non-negative")
        if shift_pattern.shift_type not in ShiftType:
            raise ValidationError(detail=f"Invalid shift type: {shift_pattern.shift_type}")
        if not shift_pattern.is_overnight and shift_pattern.start_time >= shift_pattern.end_time:
            raise ValidationError(detail="Start time must be before end time for non-overnight shifts")

        # Check for existing shift pattern with same name
        query = select(ShiftPatterns).where(
            ShiftPatterns.pattern_name == shift_pattern.pattern_name,
            ShiftPatterns.is_active.is_(True),
            ShiftPatterns.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ValidationError(detail=f"Shift pattern name '{shift_pattern.pattern_name}' already exists")

        # Create shift pattern
        db_shift_pattern = ShiftPatterns(
            **shift_pattern.model_dump(),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_shift_pattern)
        await db.commit()
        await db.refresh(db_shift_pattern)

        # Invalidate cache
        await invalidate_cache_prefix("shift_patterns")
        logger.info(f"Cache invalidated for shift_patterns", extra={"request_id": request_id})

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_SHIFT_PATTERN,
            table_affected="shift_patterns",
            record_id=db_shift_pattern.pattern_id,
            old_values=None,
            new_values=db_shift_pattern.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        # Notify admins
        admins = await get_users_with_permission(Permission.MANAGE_SHIFT_PATTERNS, db)
        for admin in admins:
            await send_email(
                to_email=admin.email,
                subject=f"New Shift Pattern Created (ID: {db_shift_pattern.pattern_id})",
                body=(
                    f"Dear {admin.first_name},\n\n"
                    f"A new shift pattern '{db_shift_pattern.pattern_name}' (ID: {db_shift_pattern.pattern_id}) has been created.\n"
                    f"Details:\n"
                    f"Shift Type: {db_shift_pattern.shift_type}\n"
                    f"Start Time: {db_shift_pattern.start_time}\n"
                    f"End Time: {db_shift_pattern.end_time}\n"
                    f"Break Duration: {db_shift_pattern.break_duration} minutes\n"
                    f"Overnight: {db_shift_pattern.is_overnight}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        logger.info(
            f"Shift pattern created, pattern_id: {db_shift_pattern.pattern_id}, name: {db_shift_pattern.pattern_name}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return ShiftPatternOut.model_validate(db_shift_pattern)

    except ValidationError as e:
        logger.error(f"Validation error creating shift pattern: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error creating shift pattern: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error creating shift pattern: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_shift_pattern(
    pattern_id: int,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_SHIFT_PATTERN]))
) -> ShiftPatternOut:
    """Retrieve a shift pattern by ID with caching."""
    try:
        if pattern_id <= 0:
            raise ValidationError(detail="Invalid pattern_id")

        cache_key = f"shift_pattern:{pattern_id}"
        cached_pattern = await get_cache(cache_key)
        if cached_pattern:
            logger.info(f"Cache hit for pattern_id: {pattern_id}", extra={"request_id": request_id})
            return ShiftPatternOut(**cached_pattern)

        await validate_shift_pattern_exists(db, pattern_id, request_id)

        query = select(ShiftPatterns).where(
            ShiftPatterns.pattern_id == pattern_id,
            ShiftPatterns.is_active.is_(True),
            ShiftPatterns.deleted_at.is_(None)
        )
        result = await db.execute(query)
        shift_pattern = result.scalar_one_or_none()

        if not shift_pattern:
            raise ShiftPatternNotFoundError(pattern_id=pattern_id)

        pattern_dict = ShiftPatternOut.model_validate(shift_pattern).model_dump()
        await set_cache(cache_key, pattern_dict, ttl=300)
        logger.info(f"Cache set for pattern_id: {pattern_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved shift pattern, pattern_id: {pattern_id}, name: {shift_pattern.pattern_name}",
            extra={"request_id": request_id}
        )
        return ShiftPatternOut.model_validate(shift_pattern)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ShiftPatternNotFoundError as e:
        logger.error(f"Shift pattern not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving shift pattern {pattern_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving shift pattern {pattern_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def list_shift_patterns(
    shift_type: Optional[ShiftType] = None,
    department_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_SHIFT_PATTERN]))
) -> List[ShiftPatternOut]:
    """Retrieve a list of active shift patterns with pagination and filtering."""
    try:
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")
        if department_id and department_id <= 0:
            raise ValidationError(detail="Invalid department_id")
        if shift_type and shift_type not in ShiftType:
            raise ValidationError(detail=f"Invalid shift type: {shift_type}")

        cache_key = f"shift_patterns_list:{shift_type or 'all'}:{department_id or 'all'}:{skip}:{limit or settings.DEFAULT_PAGE_SIZE}"
        cached_patterns = await get_cache(cache_key)
        if cached_patterns:
            logger.info(f"Cache hit for shift_patterns, shift_type: {shift_type or 'all'}, department_id: {department_id or 'all'}", extra={"request_id": request_id})
            return [ShiftPatternOut(**p) for p in cached_patterns]

        query = select(ShiftPatterns).where(
            ShiftPatterns.is_active.is_(True),
            ShiftPatterns.deleted_at.is_(None)
        )
        if shift_type:
            query = query.where(ShiftPatterns.shift_type == shift_type)

        # Restrict to department-assigned shift patterns for non-privileged users
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if department_id or not any(p == Permission.MANAGE_SHIFT_PATTERNS.value for p in user_permissions):
            query = query.join(
                ShiftAssignments,
                and_(
                    ShiftAssignments.pattern_id == ShiftPatterns.pattern_id,
                    ShiftAssignments.is_active.is_(True),
                    ShiftAssignments.deleted_at.is_(None)
                )
            ).join(
                UserDepartments,
                and_(
                    UserDepartments.user_id == ShiftAssignments.user_id,
                    UserDepartments.is_active.is_(True),
                    UserDepartments.deleted_at.is_(None)
                )
            )
            if department_id:
                query = query.where(UserDepartments.department_id == department_id)
            elif not any(p == Permission.MANAGE_SHIFT_PATTERNS.value for p in user_permissions):
                query = query.where(UserDepartments.user_id == current_user.user_id)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = query.order_by(ShiftPatterns.pattern_name.asc()).offset(skip).limit(limit)
        result = await db.execute(query)
        shift_patterns = result.scalars().all()

        patterns_dict = [ShiftPatternOut.model_validate(p).model_dump() for p in shift_patterns]
        await set_cache(cache_key, patterns_dict, ttl=300)
        logger.info(f"Cache set for shift_patterns, shift_type: {shift_type or 'all'}, department_id: {department_id or 'all'}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(shift_patterns)} shift patterns, shift_type: {shift_type or 'all'}, department_id: {department_id or 'all'}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [ShiftPatternOut.model_validate(pattern) for pattern in shift_patterns]

    except ValidationError as e:
        logger.error(f"Validation error retrieving shift patterns: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving shift patterns: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving shift patterns: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def update_shift_pattern(
    pattern_id: int,
    shift_pattern_update: ShiftPatternUpdate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.UPDATE_SHIFT_PATTERN]))
) -> ShiftPatternOut:
    """Update a shift pattern with validation, logging, and notification."""
    try:
        if pattern_id <= 0:
            raise ValidationError(detail="Invalid pattern_id")
        if shift_pattern_update.break_duration is not None and shift_pattern_update.break_duration < 0:
            raise ValidationError(detail="Break duration must be non-negative")
        if shift_pattern_update.shift_type and shift_pattern_update.shift_type not in ShiftType:
            raise ValidationError(detail=f"Invalid shift type: {shift_pattern_update.shift_type}")
        if (shift_pattern_update.start_time is not None and shift_pattern_update.end_time is not None
                and not shift_pattern_update.is_overnight and shift_pattern_update.start_time >= shift_pattern_update.end_time):
            raise ValidationError(detail="Start time must be before end time for non-overnight shifts")

        await validate_shift_pattern_exists(db, pattern_id, request_id)

        query = select(ShiftPatterns).where(
            ShiftPatterns.pattern_id == pattern_id,
            ShiftPatterns.is_active.is_(True),
            ShiftPatterns.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_shift_pattern = result.scalar_one_or_none()

        if not db_shift_pattern:
            raise ShiftPatternNotFoundError(pattern_id=pattern_id)

        update_data = shift_pattern_update.model_dump(exclude_none=True)
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        if "pattern_name" in update_data:
            query = select(ShiftPatterns).where(
                ShiftPatterns.pattern_name == update_data["pattern_name"],
                ShiftPatterns.pattern_id != pattern_id,
                ShiftPatterns.is_active.is_(True),
                ShiftPatterns.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise ValidationError(detail=f"Shift pattern name '{update_data['pattern_name']}' already exists")

        old_values = db_shift_pattern.__dict__.copy()
        for key, value in update_data.items():
            setattr(db_shift_pattern, key, value)

        db_shift_pattern.updated_at = datetime.now(timezone.utc)
        db.add(db_shift_pattern)
        await db.commit()
        await db.refresh(db_shift_pattern)

        # Invalidate caches for affected users
        query_assignments = select(ShiftAssignments).where(
            ShiftAssignments.pattern_id == pattern_id,
            ShiftAssignments.is_active.is_(True),
            ShiftAssignments.deleted_at.is_(None)
        )
        result_assignments = await db.execute(query_assignments)
        assignments = result_assignments.scalars().all()
        for assignment in assignments:
            invalidate_user_cache(assignment.user_id)

        # Invalidate cache
        await invalidate_cache_prefix("shift_patterns")
        logger.info(f"Cache invalidated for shift_patterns and {len(assignments)} users", extra={"request_id": request_id})

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_SHIFT_PATTERN,
            table_affected="shift_patterns",
            record_id=pattern_id,
            old_values=old_values,
            new_values=db_shift_pattern.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        # Notify admins
        admins = await get_users_with_permission(Permission.MANAGE_SHIFT_PATTERNS, db)
        for admin in admins:
            await send_email(
                to_email=admin.email,
                subject=f"Shift Pattern Updated (ID: {db_shift_pattern.pattern_id})",
                body=(
                    f"Dear {admin.first_name},\n\n"
                    f"The shift pattern '{db_shift_pattern.pattern_name}' (ID: {db_shift_pattern.pattern_id}) has been updated.\n"
                    f"Details:\n"
                    f"Shift Type: {db_shift_pattern.shift_type}\n"
                    f"Start Time: {db_shift_pattern.start_time}\n"
                    f"End Time: {db_shift_pattern.end_time}\n"
                    f"Break Duration: {db_shift_pattern.break_duration} minutes\n"
                    f"Overnight: {db_shift_pattern.is_overnight}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        logger.info(
            f"Shift pattern updated, pattern_id: {pattern_id}, name: {db_shift_pattern.pattern_name}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return ShiftPatternOut.model_validate(db_shift_pattern)

    except ValidationError as e:
        logger.error(f"Validation error updating shift pattern {pattern_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ShiftPatternNotFoundError as e:
        logger.error(f"Shift pattern not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error updating shift pattern {pattern_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error updating shift pattern {pattern_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def delete_shift_pattern(
    pattern_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.DELETE_SHIFT_PATTERN]))
) -> None:
    """Soft delete a shift pattern with validation, logging, and notification."""
    try:
        if pattern_id <= 0:
            raise ValidationError(detail="Invalid pattern_id")

        await validate_shift_pattern_exists(db, pattern_id, request_id)

        query = select(ShiftPatterns).where(
            ShiftPatterns.pattern_id == pattern_id,
            ShiftPatterns.is_active.is_(True),
            ShiftPatterns.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_shift_pattern = result.scalar_one_or_none()

        if not db_shift_pattern:
            raise ShiftPatternNotFoundError(pattern_id=pattern_id)

        # Check for dependent employee shift assignments
        query_assignments = select(ShiftAssignments).where(
            ShiftAssignments.pattern_id == pattern_id,
            ShiftAssignments.is_active.is_(True),
            ShiftAssignments.deleted_at.is_(None)
        )
        result_assignments = await db.execute(query_assignments)
        assignments = result_assignments.scalars().all()
        if assignments:
            raise ValidationError(detail=f"Cannot delete shift pattern with {len(assignments)} active employee assignments")

        db_shift_pattern.is_active = False
        db_shift_pattern.deleted_at = datetime.now(timezone.utc)
        db_shift_pattern.updated_at = datetime.now(timezone.utc)
        db.add(db_shift_pattern)
        await db.commit()

        # Invalidate cache
        await invalidate_cache_prefix("shift_patterns")
        logger.info(f"Cache invalidated for shift_patterns", extra={"request_id": request_id})

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_SHIFT_PATTERN,
            table_affected="shift_patterns",
            record_id=pattern_id,
            old_values=db_shift_pattern.__dict__,
            new_values=None,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        # Notify admins
        admins = await get_users_with_permission(Permission.MANAGE_SHIFT_PATTERNS, db)
        for admin in admins:
            await send_email(
                to_email=admin.email,
                subject=f"Shift Pattern Deleted (ID: {db_shift_pattern.pattern_id})",
                body=(
                    f"Dear {admin.first_name},\n\n"
                    f"The shift pattern '{db_shift_pattern.pattern_name}' (ID: {db_shift_pattern.pattern_id}) has been deleted.\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        logger.info(
            f"Shift pattern soft deleted, pattern_id: {pattern_id}, name: {db_shift_pattern.pattern_name}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error deleting shift pattern {pattern_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ShiftPatternNotFoundError as e:
        logger.error(f"Shift pattern not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error deleting shift pattern {pattern_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error deleting shift pattern {pattern_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")