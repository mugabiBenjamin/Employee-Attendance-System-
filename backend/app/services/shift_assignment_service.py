from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from datetime import date, datetime, timezone
from app.models.shift_assignments import ShiftAssignments
from app.models.users import Users
from app.models.shift_patterns import ShiftPatterns
from app.schemas.shift_assignment import ShiftAssignmentCreate, ShiftAssignmentUpdate, ShiftAssignmentOut
from app.schemas.system_log import SystemLogCreate
from app.core.config import Settings, get_settings
from app.core.enums import Permission, SystemAction
from app.core.exceptions import UserNotFoundError, ResourceNotFoundError, ValidationError, DatabaseError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_shift_assignment_exists
from app.services.system_log_service import create_system_log
from app.core.mail import send_email
import logging
from app.core.utils import get_users_with_permission

logger = logging.getLogger(__name__)

async def validate_no_overlapping_assignments(
    db: AsyncSession,
    user_id: int,
    effective_from: date,
    effective_to: Optional[date],
    assignment_id: Optional[int] = None,
    request_id: Optional[str] = None
) -> None:
    query = select(ShiftAssignments).where(
        ShiftAssignments.user_id == user_id,
        ShiftAssignments.is_active == True,
        ShiftAssignments.deleted_at == None,
        or_(
            and_(
                ShiftAssignments.effective_from <= effective_to if effective_to else True,
                ShiftAssignments.effective_to >= effective_from if ShiftAssignments.effective_to else True
            ),
            and_(
                ShiftAssignments.effective_to == None,
                ShiftAssignments.effective_from <= effective_to if effective_to else True
            ),
            and_(
                effective_to == None,
                ShiftAssignments.effective_from >= effective_from
            )
        )
    )
    if assignment_id:
        query = query.where(ShiftAssignments.assignment_id != assignment_id)
    result = await db.execute(query)
    if result.scalars().first():
        raise ValidationError(detail="Overlapping shift assignment exists for this user")

async def create_shift_assignment(
    shift_assignment: ShiftAssignmentCreate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.CREATE_SHIFT_ASSIGNMENT]))
) -> ShiftAssignmentOut:
    """
    Create a new shift assignment with validation, logging, and notification."""
    try:
        if shift_assignment.user_id <= 0 or shift_assignment.pattern_id <= 0:
            raise ValidationError(detail="Invalid user_id or pattern_id")

        # Validate user_id
        query = select(Users).where(
            Users.user_id == shift_assignment.user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            raise UserNotFoundError(user_id=shift_assignment.user_id)

        # Validate pattern_id
        query = select(ShiftPatterns).where(
            ShiftPatterns.pattern_id == shift_assignment.pattern_id,
            ShiftPatterns.is_active == True,
            ShiftPatterns.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise ResourceNotFoundError(detail=f"Shift pattern {shift_assignment.pattern_id} not found")

        # Validate overlapping assignments
        await validate_no_overlapping_assignments(
            db, shift_assignment.user_id, shift_assignment.effective_from, shift_assignment.effective_to, request_id=request_id
        )

        # Create shift assignment
        db_assignment = ShiftAssignments(
            user_id=shift_assignment.user_id,
            pattern_id=shift_assignment.pattern_id,
            effective_from=shift_assignment.effective_from,
            effective_to=shift_assignment.effective_to,
            is_active=shift_assignment.is_active,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_assignment)
        await db.commit()
        await db.refresh(db_assignment)

        # Invalidate cache
        await invalidate_cache_prefix("shift_assignments")
        logger.debug(f"Cache cleared for shift_assignments")

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_SHIFT_ASSIGNMENT,
            table_affected="shift_assignments",
            record_id=db_assignment.assignment_id,
            old_values=None,
            new_values=db_assignment.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        # Notify user and admins
        admins = await get_users_with_permission(Permission.MANAGE_SHIFT_ASSIGNMENTS, db)
        recipients = [(user.email, user.first_name)] + [(admin.email, admin.first_name) for admin in admins]
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"New Shift Assignment Created (ID: {db_assignment.assignment_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"A new shift assignment (ID: {db_assignment.assignment_id}) has been created for user ID {db_assignment.user_id}.\n"
                    f"Details:\n"
                    f"Shift Pattern ID: {db_assignment.pattern_id}\n"
                    f"Effective From: {db_assignment.effective_from}\n"
                    f"Effective To: {db_assignment.effective_to or 'Ongoing'}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        logger.info(
            f"Shift assignment created, assignment_id: {db_assignment.assignment_id}, user_id: {db_assignment.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return ShiftAssignmentOut.model_validate(db_assignment)

    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ResourceNotFoundError as e:
        logger.error(f"Resource not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error creating shift assignment: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error creating shift assignment: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def read_shift_assignment(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_SHIFT_ASSIGNMENT]))
) -> ShiftAssignmentOut:
    """
    Retrieve a shift assignment by ID with caching."""
    try:
        if assignment_id <= 0:
            raise ValidationError(detail="Invalid assignment_id")

        cache_key = f"shift_assignment:{assignment_id}"
        cached_assignment = await get_cache(cache_key)
        if cached_assignment:
            return ShiftAssignmentOut(**cached_assignment)

        await validate_shift_assignment_exists(db, assignment_id, request_id)

        query = select(ShiftAssignments).where(
            ShiftAssignments.assignment_id == assignment_id,
            ShiftAssignments.is_active == True,
            ShiftAssignments.deleted_at == None
        )
        result = await db.execute(query)
        db_assignment = result.scalar_one_or_none()

        if not db_assignment:
            raise ResourceNotFoundError(detail=f"Shift assignment {assignment_id} not found")

        assignment_dict = ShiftAssignmentOut.model_validate(db_assignment).model_dump()
        await set_cache(cache_key, assignment_dict, ttl=300)

        logger.info(
            f"Retrieved shift assignment, assignment_id: {assignment_id}",
            extra={"request_id": request_id}
        )
        return ShiftAssignmentOut.model_validate(db_assignment)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ResourceNotFoundError as e:
        logger.error(f"Shift assignment not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def read_shift_assignments(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_SHIFT_ASSIGNMENT]))
) -> List[ShiftAssignmentOut]:
    """
    Retrieve a list of shift assignments with optional user ID filter and pagination."""
    try:
        limit = limit or settings.DEFAULT_PAGE_SIZE
        if skip < 0 or limit <= 0:
            raise ValidationError(detail="Invalid pagination parameters")

        cache_key = f"shift_assignments:{user_id or 'all'}:{skip}:{limit}"
        cached_assignments = await get_cache(cache_key)
        if cached_assignments:
            return [ShiftAssignmentOut(**a) for a in cached_assignments]

        if user_id:
            if user_id <= 0:
                raise ValidationError(detail="Invalid user_id")
            query = select(Users).where(
                Users.user_id == user_id,
                Users.is_active == True,
                Users.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise UserNotFoundError(user_id=user_id)

        query = select(ShiftAssignments).where(
            ShiftAssignments.is_active == True,
            ShiftAssignments.deleted_at == None
        )
        if user_id:
            query = query.where(ShiftAssignments.user_id == user_id)
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        assignments = result.scalars().all()

        assignments_dict = [ShiftAssignmentOut.model_validate(a).model_dump() for a in assignments]
        await set_cache(cache_key, assignments_dict, ttl=300)

        logger.info(
            f"Retrieved {len(assignments)} shift assignments",
            extra={"request_id": request_id, "user_id": user_id}
        )
        return [ShiftAssignmentOut.model_validate(assignment) for assignment in assignments]

    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving shift assignments: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving shift assignments: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def update_shift_assignment(
    assignment_id: int,
    shift_assignment_update: ShiftAssignmentUpdate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.UPDATE_SHIFT_ASSIGNMENT]))
) -> ShiftAssignmentOut:
    """
    Update a shift assignment with validation, logging, and notification."""
    try:
        if assignment_id <= 0:
            raise ValidationError(detail="Invalid assignment_id")

        await validate_shift_assignment_exists(db, assignment_id, request_id)

        query = select(ShiftAssignments).where(
            ShiftAssignments.assignment_id == assignment_id,
            ShiftAssignments.is_active == True,
            ShiftAssignments.deleted_at == None
        )
        result = await db.execute(query)
        db_assignment = result.scalar_one_or_none()

        if not db_assignment:
            raise ResourceNotFoundError(detail=f"Shift assignment {assignment_id} not found")

        update_data = shift_assignment_update.model_dump(exclude_none=True)
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        if "pattern_id" in update_data:
            query = select(ShiftPatterns).where(
                ShiftPatterns.pattern_id == update_data["pattern_id"],
                ShiftPatterns.is_active == True,
                ShiftPatterns.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise ResourceNotFoundError(detail=f"Shift pattern {update_data['pattern_id']} not found")

        # Validate overlapping assignments if dates are updated
        effective_from = update_data.get("effective_from", db_assignment.effective_from)
        effective_to = update_data.get("effective_to", db_assignment.effective_to)
        if "effective_from" in update_data or "effective_to" in update_data:
            await validate_no_overlapping_assignments(
                db, db_assignment.user_id, effective_from, effective_to, assignment_id, request_id
            )

        old_values = db_assignment.__dict__.copy()
        for key, value in update_data.items():
            setattr(db_assignment, key, value)

        db_assignment.updated_at = datetime.now(timezone.utc)
        db.add(db_assignment)
        await db.commit()
        await db.refresh(db_assignment)

        # Invalidate cache
        await invalidate_cache_prefix("shift_assignments")
        logger.debug(f"Cache cleared for shift_assignments")

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_SHIFT_ASSIGNMENT,
            table_affected="shift_assignments",
            record_id=assignment_id,
            old_values=old_values,
            new_values=db_assignment.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        # Notify user and admins
        query_user = select(Users).where(Users.user_id == db_assignment.user_id)
        result_user = await db.execute(query_user)
        user = result_user.scalar_one_or_none()
        if user:
            await send_email(
                to_email=user.email,
                subject=f"Shift Assignment Updated (ID: {db_assignment.assignment_id})",
                body=(
                    f"Dear {user.first_name},\n\n"
                    f"Your shift assignment (ID: {db_assignment.assignment_id}) has been updated.\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )
        
        # Notify admins
        admins = await get_users_with_permission(Permission.MANAGE_SHIFT_ASSIGNMENTS, db)
        for admin in admins:
            await send_email(
                to_email=admin.email,
                subject=f"Shift Assignment Updated (ID: {db_assignment.assignment_id})",
                body=(
                    f"Dear {admin.first_name},\n\n"
                    f"The shift assignment (ID: {db_assignment.assignment_id}) for user ID {db_assignment.user_id} has been updated.\n"
                    f"Details:\n"
                    f"Pattern ID: {db_assignment.pattern_id}\n"
                    f"Start Date: {db_assignment.effective_from}\n"
                    f"End Date: {db_assignment.effective_to}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        logger.info(
            f"Shift assignment updated, assignment_id: {assignment_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return ShiftAssignmentOut.model_validate(db_assignment)

    except ResourceNotFoundError as e:
        logger.error(f"Resource not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error updating shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error updating shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def delete_shift_assignment(
    assignment_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.DELETE_SHIFT_ASSIGNMENT]))
) -> None:
    """
    Soft delete a shift assignment with logging and notification."""
    try:
        if assignment_id <= 0:
            raise ValidationError(detail="Invalid assignment_id")

        await validate_shift_assignment_exists(db, assignment_id, request_id)

        query = select(ShiftAssignments).where(
            ShiftAssignments.assignment_id == assignment_id,
            ShiftAssignments.is_active == True,
            ShiftAssignments.deleted_at == None
        )
        result = await db.execute(query)
        db_assignment = result.scalar_one_or_none()

        if not db_assignment:
            raise ResourceNotFoundError(detail=f"Shift assignment {assignment_id} not found")

        db_assignment.is_active = False
        db_assignment.deleted_at = datetime.now(timezone.utc)
        db_assignment.updated_at = datetime.now(timezone.utc)
        db.add(db_assignment)
        await db.commit()

        # Invalidate cache
        await invalidate_cache_prefix("shift_assignments")
        logger.debug(f"Cache cleared for shift_assignments")

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_SHIFT_ASSIGNMENT,
            table_affected="shift_assignments",
            record_id=assignment_id,
            old_values=db_assignment.__dict__,
            new_values=None,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        # Notify user and admins
        query_user = select(Users).where(Users.user_id == db_assignment.user_id)
        result_user = await db.execute(query_user)
        user = result_user.scalar_one_or_none()
        # Notify admins
        admins = await get_users_with_permission(Permission.MANAGE_SHIFT_ASSIGNMENTS, db)
        for admin in admins:
            await send_email(
                to_email=admin.email,
                subject=f"Shift Assignment Deleted (ID: {db_assignment.assignment_id})",
                body=(
                    f"Dear {admin.first_name},\n\n"
                    f"The shift assignment (ID: {db_assignment.assignment_id}) for user ID {db_assignment.user_id} has been deleted.\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        # Notify user and admins
        if user:
            await send_email(
                to_email=user.email,
                subject=f"Shift Assignment Deleted (ID: {db_assignment.assignment_id})",
                body=(
                    f"Dear {user.first_name},\n\n"
                    f"Your shift assignment (ID: {db_assignment.assignment_id}) has been deleted.\n"
                    f"Please contact HR for any questions.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        logger.info(
            f"Shift assignment soft deleted, assignment_id: {assignment_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ResourceNotFoundError as e:
        logger.error(f"Shift assignment not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error deleting shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error deleting shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_my_shift_assignments(
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_OWN_SHIFT_ASSIGNMENT]))
) -> List[ShiftAssignmentOut]:
    """
    Retrieve the current user's shift assignments with pagination and caching."""
    try:
        limit = limit or settings.DEFAULT_PAGE_SIZE
        if skip < 0 or limit <= 0:
            raise ValidationError(detail="Invalid pagination parameters")

        cache_key = f"shift_assignments:user:{current_user.user_id}:{skip}:{limit}"
        cached_assignments = await get_cache(cache_key)
        if cached_assignments:
            return [ShiftAssignmentOut(**a) for a in cached_assignments]

        query = select(ShiftAssignments).where(
            ShiftAssignments.user_id == current_user.user_id,
            ShiftAssignments.is_active == True,
            ShiftAssignments.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        assignments = result.scalars().all()

        assignments_dict = [ShiftAssignmentOut.model_validate(a).model_dump() for a in assignments]
        await set_cache(cache_key, assignments_dict, ttl=300)

        logger.info(
            f"Retrieved {len(assignments)} shift assignments for user_id: {current_user.user_id}",
            extra={"request_id": request_id}
        )
        return [ShiftAssignmentOut.model_validate(assignment) for assignment in assignments]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving shift assignments for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving shift assignments for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")