from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from datetime import date, datetime, timezone
from app.models.shift_assignments import ShiftAssignments
from app.models.users import Users
from app.models.shift_patterns import ShiftPatterns
from app.models.user_departments import UserDepartments
from app.models.employee_hierarchy import EmployeeHierarchy
from app.schemas.shift_assignment import ShiftAssignmentCreate, ShiftAssignmentUpdate, ShiftAssignmentOut
from app.schemas.system_log import SystemLogCreate
from app.core.config import Settings, get_settings
from app.core.enums import Permission, SystemAction
from app.core.exceptions import UserNotFoundError, ResourceNotFoundError, ValidationError
from app.core.security import get_current_user
from app.core.permissions import require_permissions_dependency, invalidate_user_cache, get_user_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_shift_assignment_exists, validate_department_exists
from app.core.utils import get_request_id, get_users_with_permission
from app.services.system_log_service import create_system_log
from app.core.mail import send_email
import logging

logger = logging.getLogger(__name__)

async def validate_no_overlapping_assignments(
    db: AsyncSession,
    user_id: int,
    effective_from: date,
    effective_to: Optional[date],
    assignment_id: Optional[int] = None,
    request_id: Optional[str] = None
) -> None:
    """Validate that no overlapping shift assignments exist for the user."""
    query = select(ShiftAssignments).where(
        ShiftAssignments.user_id == user_id,
        ShiftAssignments.is_active.is_(True),
        ShiftAssignments.deleted_at.is_(None),
        or_(
            and_(
                ShiftAssignments.effective_from <= (effective_to if effective_to else date.max),
                ShiftAssignments.effective_to >= effective_from if ShiftAssignments.effective_to else True
            ),
            and_(
                ShiftAssignments.effective_to.is_(None),
                ShiftAssignments.effective_from <= (effective_to if effective_to else date.max)
            ),
            and_(
                effective_to is None,
                ShiftAssignments.effective_from >= effective_from
            )
        )
    )
    if assignment_id:
        query = query.where(ShiftAssignments.assignment_id != assignment_id)
    result = await db.execute(query)
    conflicting_assignment = result.scalars().first()
    if conflicting_assignment:
        raise ValidationError(
            detail=f"Overlapping shift assignment exists for user ID {user_id}: "
                   f"Assignment ID {conflicting_assignment.assignment_id} "
                   f"(from {conflicting_assignment.effective_from} to "
                   f"{conflicting_assignment.effective_to or 'ongoing'})"
        )

async def create_shift_assignment(
    shift_assignment: ShiftAssignmentCreate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.CREATE_SHIFT_ASSIGNMENT]))
) -> ShiftAssignmentOut:
    """Create a new shift assignment with validation, logging, and notification."""
    try:
        if shift_assignment.user_id <= 0 or shift_assignment.pattern_id <= 0:
            raise ValidationError(detail="Invalid user_id or pattern_id")
        if shift_assignment.effective_from < date.today():
            raise ValidationError(detail="Effective from date cannot be in the past")
        if shift_assignment.effective_to and shift_assignment.effective_to < shift_assignment.effective_from:
            raise ValidationError(detail="Effective to date must be after effective from date")

        # Validate user_id
        query = select(Users).where(
            Users.user_id == shift_assignment.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            raise UserNotFoundError(user_id=shift_assignment.user_id)

        # Validate pattern_id
        query = select(ShiftPatterns).where(
            ShiftPatterns.pattern_id == shift_assignment.pattern_id,
            ShiftPatterns.is_active.is_(True),
            ShiftPatterns.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise ResourceNotFoundError(detail=f"Shift pattern ID {shift_assignment.pattern_id} not found")

        # Validate overlapping assignments
        await validate_no_overlapping_assignments(
            db, shift_assignment.user_id, shift_assignment.effective_from, shift_assignment.effective_to, request_id=request_id
        )

        # Create shift assignment
        db_assignment = ShiftAssignments(
            **shift_assignment.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_assignment)
        await db.commit()
        await db.refresh(db_assignment)

        # Invalidate caches
        await invalidate_cache_prefix("shift_assignments")
        invalidate_user_cache(shift_assignment.user_id)
        invalidate_user_cache(current_user.user_id)  # Invalidate current user's cache for permission updates
        logger.info(
            f"Cache invalidated for shift_assignments, user_id: {shift_assignment.user_id}, and current_user: {current_user.user_id}",
            extra={"request_id": request_id}
        )

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
        await create_system_log(log, request, current_user, db, request_id)

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
    except Exception as e:
        logger.error(f"Unexpected error creating shift assignment: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating shift assignment")

async def read_shift_assignment(
    assignment_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_SHIFT_ASSIGNMENT, Permission.VIEW_OWN_SHIFT_ASSIGNMENT]))
) -> ShiftAssignmentOut:
    """Retrieve a shift assignment by ID with caching."""
    try:
        if assignment_id <= 0:
            raise ValidationError(detail="Invalid assignment_id")

        cache_key = f"shift_assignment:{assignment_id}"
        cached_assignment = await get_cache(cache_key)
        if cached_assignment:
            logger.info(f"Cache hit for assignment_id: {assignment_id}", extra={"request_id": request_id})
            return ShiftAssignmentOut(**cached_assignment)

        await validate_shift_assignment_exists(db, assignment_id, request_id)

        query = select(ShiftAssignments).where(
            ShiftAssignments.assignment_id == assignment_id,
            ShiftAssignments.is_active.is_(True),
            ShiftAssignments.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_assignment = result.scalar_one_or_none()

        if not db_assignment:
            raise ResourceNotFoundError(detail=f"Shift assignment ID {assignment_id} not found")

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if Permission.VIEW_SHIFT_ASSIGNMENT not in user_permissions and Permission.MANAGE_SHIFT_ASSIGNMENTS not in user_permissions:
            if db_assignment.user_id != current_user.user_id:
                query_supervisor = select(EmployeeHierarchy).where(
                    EmployeeHierarchy.supervisor_id == current_user.user_id,
                    EmployeeHierarchy.employee_id == db_assignment.user_id,
                    EmployeeHierarchy.is_active.is_(True),
                    EmployeeHierarchy.deleted_at.is_(None)
                )
                result_supervisor = await db.execute(query_supervisor)
                if not result_supervisor.scalar_one_or_none():
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized to view this shift assignment"
                    )

        assignment_dict = ShiftAssignmentOut.model_validate(db_assignment).model_dump()
        await set_cache(cache_key, assignment_dict, ttl=300)
        logger.info(f"Cache set for assignment_id: {assignment_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved shift assignment, assignment_id: {assignment_id}, user_id: {db_assignment.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return ShiftAssignmentOut.model_validate(db_assignment)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ResourceNotFoundError as e:
        logger.error(f"Shift assignment not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Forbidden access to shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving shift assignment")

async def read_shift_assignments(
    user_id: Optional[int] = None,
    pattern_id: Optional[int] = None,
    department_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_SHIFT_ASSIGNMENT, Permission.VIEW_OWN_SHIFT_ASSIGNMENT]))
) -> List[ShiftAssignmentOut]:
    """Retrieve a list of shift assignments with optional filters and pagination."""
    try:
        limit = limit or settings.DEFAULT_PAGE_SIZE
        if skip < 0 or limit <= 0:
            raise ValidationError(detail="Invalid pagination parameters")
        if user_id and user_id <= 0:
            raise ValidationError(detail="Invalid user_id")
        if pattern_id and pattern_id <= 0:
            raise ValidationError(detail="Invalid pattern_id")
        if department_id and department_id <= 0:
            raise ValidationError(detail="Invalid department_id")

        cache_key = f"shift_assignments:{user_id or 'all'}:{pattern_id or 'all'}:{department_id or 'all'}:{skip}:{limit}"
        cached_assignments = await get_cache(cache_key)
        if cached_assignments:
            logger.info(f"Cache hit for shift_assignments, user_id: {user_id or 'all'}, pattern_id: {pattern_id or 'all'}", extra={"request_id": request_id})
            return [ShiftAssignmentOut(**a) for a in cached_assignments]

        # Validate inputs
        if user_id:
            query = select(Users).where(
                Users.user_id == user_id,
                Users.is_active.is_(True),
                Users.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise UserNotFoundError(user_id=user_id)

        if pattern_id:
            query = select(ShiftPatterns).where(
                ShiftPatterns.pattern_id == pattern_id,
                ShiftPatterns.is_active.is_(True),
                ShiftPatterns.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise ResourceNotFoundError(detail=f"Shift pattern ID {pattern_id} not found")

        if department_id:
            await validate_department_exists(db, department_id, request_id)

        query = select(ShiftAssignments).where(
            ShiftAssignments.is_active.is_(True),
            ShiftAssignments.deleted_at.is_(None)
        )
        if user_id:
            query = query.where(ShiftAssignments.user_id == user_id)
        if pattern_id:
            query = query.where(ShiftAssignments.pattern_id == pattern_id)
        if department_id:
            query = query.join(
                UserDepartments,
                and_(
                    UserDepartments.user_id == ShiftAssignments.user_id,
                    UserDepartments.department_id == department_id,
                    UserDepartments.is_active.is_(True),
                    UserDepartments.deleted_at.is_(None)
                )
            )

        # Restrict to own or subordinate assignments for non-privileged users
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if Permission.VIEW_SHIFT_ASSIGNMENT not in user_permissions and Permission.MANAGE_SHIFT_ASSIGNMENTS not in user_permissions:
            query_subordinates = select(EmployeeHierarchy.employee_id).where(
                EmployeeHierarchy.supervisor_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result_subordinates = await db.execute(query_subordinates)
            subordinate_ids = [row.employee_id for row in result_subordinates]
            query = query.where(
                or_(
                    ShiftAssignments.user_id == current_user.user_id,
                    ShiftAssignments.user_id.in_(subordinate_ids)
                )
            )

        query = query.order_by(ShiftAssignments.effective_from.asc()).offset(skip).limit(limit)
        result = await db.execute(query)
        assignments = result.scalars().all()

        assignments_dict = [ShiftAssignmentOut.model_validate(a).model_dump() for a in assignments]
        await set_cache(cache_key, assignments_dict, ttl=300)
        logger.info(f"Cache set for shift_assignments, user_id: {user_id or 'all'}, pattern_id: {pattern_id or 'all'}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(assignments)} shift assignments, user_id: {user_id or 'all'}, pattern_id: {pattern_id or 'all'}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [ShiftAssignmentOut.model_validate(assignment) for assignment in assignments]

    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ResourceNotFoundError as e:
        logger.error(f"Resource not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving shift assignments: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving shift assignments")

async def update_shift_assignment(
    assignment_id: int,
    shift_assignment_update: ShiftAssignmentUpdate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.UPDATE_SHIFT_ASSIGNMENT]))
) -> ShiftAssignmentOut:
    """Update a shift assignment with validation, logging, and notification."""
    try:
        if assignment_id <= 0:
            raise ValidationError(detail="Invalid assignment_id")
        if shift_assignment_update.effective_from and shift_assignment_update.effective_from < date.today():
            raise ValidationError(detail="Effective from date cannot be in the past")
        if (shift_assignment_update.effective_to and shift_assignment_update.effective_from
                and shift_assignment_update.effective_to < shift_assignment_update.effective_from):
            raise ValidationError(detail="Effective to date must be after effective from date")

        await validate_shift_assignment_exists(db, assignment_id, request_id)

        query = select(ShiftAssignments).where(
            ShiftAssignments.assignment_id == assignment_id,
            ShiftAssignments.is_active.is_(True),
            ShiftAssignments.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_assignment = result.scalar_one_or_none()

        if not db_assignment:
            raise ResourceNotFoundError(detail=f"Shift assignment ID {assignment_id} not found")

        update_data = shift_assignment_update.model_dump(exclude_none=True)
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        if "pattern_id" in update_data:
            query = select(ShiftPatterns).where(
                ShiftPatterns.pattern_id == update_data["pattern_id"],
                ShiftPatterns.is_active.is_(True),
                ShiftPatterns.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise ResourceNotFoundError(detail=f"Shift pattern ID {update_data['pattern_id']} not found")

        if "user_id" in update_data:
            query = select(Users).where(
                Users.user_id == update_data["user_id"],
                Users.is_active.is_(True),
                Users.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise UserNotFoundError(user_id=update_data["user_id"])

        # Validate overlapping assignments if dates or user_id are updated
        effective_from = update_data.get("effective_from", db_assignment.effective_from)
        effective_to = update_data.get("effective_to", db_assignment.effective_to)
        user_id = update_data.get("user_id", db_assignment.user_id)
        if "effective_from" in update_data or "effective_to" in update_data or "user_id" in update_data:
            await validate_no_overlapping_assignments(
                db, user_id, effective_from, effective_to, assignment_id, request_id
            )

        old_values = db_assignment.__dict__.copy()
        for key, value in update_data.items():
            setattr(db_assignment, key, value)

        db_assignment.updated_at = datetime.now(timezone.utc)
        db.add(db_assignment)
        await db.commit()
        await db.refresh(db_assignment)

        # Invalidate caches
        await invalidate_cache_prefix("shift_assignments")
        invalidate_user_cache(db_assignment.user_id)
        invalidate_user_cache(current_user.user_id)  # Invalidate current user's cache for permission updates
        logger.info(
            f"Cache invalidated for shift_assignments, user_id: {db_assignment.user_id}, and current_user: {current_user.user_id}",
            extra={"request_id": request_id}
        )

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
        await create_system_log(log, request, current_user, db, request_id)

        # Notify user and admins
        query_user = select(Users).where(
            Users.user_id == db_assignment.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_user = await db.execute(query_user)
        user = result_user.scalar_one_or_none()
        if user:
            await send_email(
                to_email=user.email,
                subject=f"Shift Assignment Updated (ID: {db_assignment.assignment_id})",
                body=(
                    f"Dear {user.first_name},\n\n"
                    f"Your shift assignment (ID: {db_assignment.assignment_id}) has been updated.\n"
                    f"Details:\n"
                    f"Shift Pattern ID: {db_assignment.pattern_id}\n"
                    f"Effective From: {db_assignment.effective_from}\n"
                    f"Effective To: {db_assignment.effective_to or 'Ongoing'}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        admins = await get_users_with_permission(Permission.MANAGE_SHIFT_ASSIGNMENTS, db)
        for admin in admins:
            await send_email(
                to_email=admin.email,
                subject=f"Shift Assignment Updated (ID: {db_assignment.assignment_id})",
                body=(
                    f"Dear {admin.first_name},\n\n"
                    f"The shift assignment (ID: {db_assignment.assignment_id}) for user ID {db_assignment.user_id} has been updated.\n"
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
            f"Shift assignment updated, assignment_id: {assignment_id}, user_id: {db_assignment.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return ShiftAssignmentOut.model_validate(db_assignment)

    except ResourceNotFoundError as e:
        logger.error(f"Resource not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error updating shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating shift assignment")

async def delete_shift_assignment(
    assignment_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.DELETE_SHIFT_ASSIGNMENT]))
) -> None:
    """Soft delete a shift assignment with validation, logging, and notification."""
    try:
        if assignment_id <= 0:
            raise ValidationError(detail="Invalid assignment_id")

        await validate_shift_assignment_exists(db, assignment_id, request_id)

        query = select(ShiftAssignments).where(
            ShiftAssignments.assignment_id == assignment_id,
            ShiftAssignments.is_active.is_(True),
            ShiftAssignments.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_assignment = result.scalar_one_or_none()

        if not db_assignment:
            raise ResourceNotFoundError(detail=f"Shift assignment ID {assignment_id} not found")

        # Optional: Check if this is the only active assignment for the user
        if settings.REQUIRE_ACTIVE_SHIFT_ASSIGNMENT:
            query_check = select(ShiftAssignments).where(
                ShiftAssignments.user_id == db_assignment.user_id,
                ShiftAssignments.assignment_id != assignment_id,
                ShiftAssignments.is_active.is_(True),
                ShiftAssignments.deleted_at.is_(None)
            )
            result_check = await db.execute(query_check)
            if not result_check.scalars().all():
                raise ValidationError(detail=f"Cannot delete the only active shift assignment for user ID {db_assignment.user_id}")

        db_assignment.is_active = False
        db_assignment.deleted_at = datetime.now(timezone.utc)
        db_assignment.updated_at = datetime.now(timezone.utc)
        db.add(db_assignment)
        await db.commit()

        # Invalidate caches
        await invalidate_cache_prefix("shift_assignments")
        invalidate_user_cache(db_assignment.user_id)
        invalidate_user_cache(current_user.user_id)  # Invalidate current user's cache for permission updates
        logger.info(
            f"Cache invalidated for shift_assignments, user_id: {db_assignment.user_id}, and current_user: {current_user.user_id}",
            extra={"request_id": request_id}
        )

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
        await create_system_log(log, request, current_user, db, request_id)

        # Notify user and admins
        query_user = select(Users).where(
            Users.user_id == db_assignment.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_user = await db.execute(query_user)
        user = result_user.scalar_one_or_none()
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

        logger.info(
            f"Shift assignment soft deleted, assignment_id: {assignment_id}, user_id: {db_assignment.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ResourceNotFoundError as e:
        logger.error(f"Shift assignment not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error deleting shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting shift assignment")

async def get_my_shift_assignments(
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_OWN_SHIFT_ASSIGNMENT]))
) -> List[ShiftAssignmentOut]:
    """Retrieve the current user's shift assignments with pagination and caching."""
    try:
        limit = limit or settings.DEFAULT_PAGE_SIZE
        if skip < 0 or limit <= 0:
            raise ValidationError(detail="Invalid pagination parameters")

        cache_key = f"shift_assignments:user:{current_user.user_id}:{skip}:{limit}"
        cached_assignments = await get_cache(cache_key)
        if cached_assignments:
            logger.info(f"Cache hit for shift_assignments, user_id: {current_user.user_id}", extra={"request_id": request_id})
            return [ShiftAssignmentOut(**a) for a in cached_assignments]

        query = select(ShiftAssignments).where(
            ShiftAssignments.user_id == current_user.user_id,
            ShiftAssignments.is_active.is_(True),
            ShiftAssignments.deleted_at.is_(None)
        ).order_by(ShiftAssignments.effective_from.asc()).offset(skip).limit(limit)
        result = await db.execute(query)
        assignments = result.scalars().all()

        assignments_dict = [ShiftAssignmentOut.model_validate(a).model_dump() for a in assignments]
        await set_cache(cache_key, assignments_dict, ttl=300)
        logger.info(f"Cache set for shift_assignments, user_id: {current_user.user_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(assignments)} shift assignments for user_id: {current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [ShiftAssignmentOut.model_validate(assignment) for assignment in assignments]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving shift assignments for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving shift assignments")