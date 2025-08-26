from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.user_departments import UserDepartments
from app.models.users import Users
from app.models.employee_hierarchy import EmployeeHierarchy
from app.schemas.user_department import UserDepartmentCreate, UserDepartmentUpdate, UserDepartmentOut
from app.schemas.system_log import SystemLogCreate
from app.core.enums import SystemAction, Permission
from app.core.exceptions import UserDepartmentNotFoundError, DatabaseError, ResourceConflictError, UserNotFoundError, DepartmentNotFoundError, ValidationError
from app.core.security import get_current_user
from app.core.permissions import require_permissions, get_user_permissions, invalidate_cache_prefix
from app.services.system_log_service import create_system_log
from app.core.validators import validate_user_exists, validate_department_exists
from app.core.config import Settings, get_settings
from app.core.database import get_db, get_cache, set_cache
from app.core.utils import get_request_id
import logging

logger = logging.getLogger(__name__)

async def _check_user_authorization(
    db: AsyncSession,
    current_user: Users,
    target_user_id: int,
    required_permissions: List[Permission],
    request_id: Optional[str] = None
) -> bool:
    """Check if the current user is authorized to perform actions on the target user's department assignments."""
    user_permissions = await get_user_permissions(current_user.user_id, db)
    if target_user_id == current_user.user_id and Permission.VIEW_OWN_DEPARTMENT.value in user_permissions:
        return True
    if any(p.value in user_permissions for p in required_permissions):
        return True
    query_hierarchy = select(EmployeeHierarchy).where(
        EmployeeHierarchy.employee_id == target_user_id,
        EmployeeHierarchy.supervisor_id == current_user.user_id,
        EmployeeHierarchy.is_active.is_(True),
        EmployeeHierarchy.deleted_at.is_(None)
    )
    result_hierarchy = await db.execute(query_hierarchy)
    supervisor_check = bool(result_hierarchy.scalar_one_or_none())
    logger.debug(
        f"Authorization check for user_id={current_user.user_id} on target_user_id={target_user_id}: "
        f"has_permissions={any(p.value in user_permissions for p in required_permissions)}, is_supervisor={supervisor_check}",
        extra={"request_id": request_id}
    )
    return supervisor_check

async def create_user_department(
    user_department: UserDepartmentCreate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.CREATE_USER_DEPARTMENT]))
) -> UserDepartmentOut:
    """Create a new user-department assignment with validation, logging, and cache clearing."""
    try:
        # Validate user, department, and assigned_by
        await validate_user_exists(db, user_department.user_id, request_id)
        await validate_department_exists(db, user_department.department_id, request_id)
        if user_department.assigned_by:
            await validate_user_exists(db, user_department.assigned_by, request_id)

        # Authorization check
        if not await _check_user_authorization(
            db, current_user, user_department.user_id, [Permission.CREATE_USER_DEPARTMENT, Permission.MANAGE_EMPLOYEES], request_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to assign this user to a department"
            )

        # Check for existing assignment
        if await _assignment_exists(db, user_department.user_id, user_department.department_id, request_id=request_id):
            raise ResourceConflictError(detail="User is already assigned to this department")

        # Handle primary assignment logic
        if user_department.is_primary:
            await _clear_existing_primary(db, user_department.user_id, request_id=request_id)

        # Create assignment
        db_user_department = UserDepartments(
            user_id=user_department.user_id,
            department_id=user_department.department_id,
            assigned_by=user_department.assigned_by or current_user.user_id,
            is_primary=user_department.is_primary,
            is_active=user_department.is_active,
            assigned_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_user_department)
        await db.commit()
        await db.refresh(db_user_department)

        # Invalidate caches
        await invalidate_cache_prefix("user_department")
        await invalidate_cache_prefix(f"user:{user_department.user_id}")
        await invalidate_cache_prefix(f"department:{user_department.department_id}")
        logger.info(
            f"Cache invalidated for user_department, user:{user_department.user_id}, department:{user_department.department_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_USER_DEPARTMENT,
            table_affected="user_departments",
            record_id=db_user_department.user_department_id,
            old_values=None,
            new_values=db_user_department.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"User department assignment created: user_department_id={db_user_department.user_department_id}, user_id={user_department.user_id}, department_id={user_department.department_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return UserDepartmentOut.model_validate(db_user_department)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DepartmentNotFoundError as e:
        logger.error(f"Department not found: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ResourceConflictError as e:
        logger.error(f"Resource conflict: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error creating user department: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except DatabaseError as e:
        logger.error(f"Database error creating user department: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error creating user department: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def read_user_department(
    user_department_id: int,
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_USER_DEPARTMENT]))
) -> UserDepartmentOut:
    """Retrieve a user-department assignment by ID."""
    try:
        if user_department_id <= 0:
            raise ValidationError(detail="Invalid user-department ID")

        cache_key = f"user_department:{user_department_id}"
        cached_user_department = await get_cache(cache_key)
        if cached_user_department:
            logger.info(f"Cache hit for user_department_id: {user_department_id}", extra={"request_id": request_id})
            return UserDepartmentOut(**cached_user_department)

        query = select(UserDepartments).where(
            UserDepartments.user_department_id == user_department_id,
            UserDepartments.is_active.is_(True),
            UserDepartments.deleted_at.is_(None)
        )
        result = await db.execute(query)
        user_department = result.scalar_one_or_none()

        if not user_department:
            raise UserDepartmentNotFoundError(user_department_id=user_department_id)

        user_department_dict = UserDepartmentOut.model_validate(user_department).model_dump()
        await set_cache(cache_key, user_department_dict, ttl=300)
        logger.info(f"Cache set for user_department_id: {user_department_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved user department: user_department_id={user_department_id}",
            extra={"request_id": request_id}
        )
        return UserDepartmentOut.model_validate(user_department)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserDepartmentNotFoundError as e:
        logger.error(f"User department not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving user department {user_department_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving user department {user_department_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def read_user_departments(
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_USER_DEPARTMENT]))
) -> List[UserDepartmentOut]:
    """List user-department assignments with optional filters and pagination."""
    try:
        if skip < 0 or (limit is not None and limit < 0):
            raise ValidationError(detail="Invalid pagination parameters")
        if user_id and user_id <= 0:
            raise ValidationError(detail="Invalid user ID")
        if department_id and department_id <= 0:
            raise ValidationError(detail="Invalid department ID")

        # Authorization check for user_id
        if user_id and not await _check_user_authorization(
            db, current_user, user_id, [Permission.VIEW_USER_DEPARTMENT, Permission.MANAGE_EMPLOYEES], request_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view department assignments for this user"
            )

        limit = limit or settings.DEFAULT_PAGE_SIZE
        cache_key = f"user_departments:{user_id or 'all'}:{department_id or 'all'}:{skip}:{limit}"
        cached_user_departments = await get_cache(cache_key)
        if cached_user_departments:
            logger.info(
                f"Cache hit for user_departments, user_id: {user_id or 'all'}, department_id: {department_id or 'all'}",
                extra={"request_id": request_id, "user_id": current_user.user_id}
            )
            return [UserDepartmentOut(**ud) for ud in cached_user_departments]

        query = select(UserDepartments).where(
            UserDepartments.is_active.is_(True),
            UserDepartments.deleted_at.is_(None)
        )

        if user_id:
            await validate_user_exists(db, user_id, request_id)
            query = query.where(UserDepartments.user_id == user_id)

        if department_id:
            await validate_department_exists(db, department_id, request_id)
            query = query.where(UserDepartments.department_id == department_id)

        query = query.order_by(UserDepartments.is_primary.desc(), UserDepartments.assigned_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        user_departments = result.scalars().all()

        user_departments_dict = [UserDepartmentOut.model_validate(ud).model_dump() for ud in user_departments]
        await set_cache(cache_key, user_departments_dict, ttl=300)
        logger.info(
            f"Cache set for user_departments, user_id: {user_id or 'all'}, department_id: {department_id or 'all'}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

        logger.info(
            f"Retrieved {len(user_departments)} user department assignments",
            extra={"request_id": request_id, "user_id": current_user.user_id, "target_user_id": user_id, "department_id": department_id}
        )
        return [UserDepartmentOut.model_validate(ud) for ud in user_departments]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DepartmentNotFoundError as e:
        logger.error(f"Department not found: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error retrieving user departments: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except DatabaseError as e:
        logger.error(f"Database error retrieving user departments: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving user departments: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def update_user_department(
    user_department_id: int,
    update_data: UserDepartmentUpdate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.UPDATE_USER_DEPARTMENT]))
) -> UserDepartmentOut:
    """Update a user-department assignment with validation, logging, and cache clearing."""
    try:
        if user_department_id <= 0:
            raise ValidationError(detail="Invalid user-department ID")

        # Get existing assignment
        query = select(UserDepartments).where(
            UserDepartments.user_department_id == user_department_id,
            UserDepartments.is_active.is_(True),
            UserDepartments.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_user_department = result.scalar_one_or_none()

        if not db_user_department:
            raise UserDepartmentNotFoundError(user_department_id=user_department_id)

        # Authorization check
        if not await _check_user_authorization(
            db, current_user, db_user_department.user_id, [Permission.UPDATE_USER_DEPARTMENT, Permission.MANAGE_EMPLOYEES], request_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this user's department assignment"
            )

        changes = update_data.model_dump(exclude_none=True)
        if not changes:
            raise ValidationError(detail="No fields provided for update")

        # Validate changes
        old_user_id = db_user_department.user_id
        old_department_id = db_user_department.department_id
        if "user_id" in changes:
            await validate_user_exists(db, changes["user_id"], request_id)

        if "department_id" in changes:
            await validate_department_exists(db, changes["department_id"], request_id)
            new_user_id = changes.get("user_id", db_user_department.user_id)
            if await _assignment_exists(db, new_user_id, changes["department_id"], exclude_id=user_department_id, request_id=request_id):
                raise ResourceConflictError(detail="User is already assigned to this department")

        if "assigned_by" in changes and changes["assigned_by"]:
            await validate_user_exists(db, changes["assigned_by"], request_id)

        # Handle primary assignment logic
        if changes.get("is_primary", False):
            user_id = changes.get("user_id", db_user_department.user_id)
            await _clear_existing_primary(db, user_id, exclude_id=user_department_id, request_id=request_id)

        # Store old values for logging
        old_values = db_user_department.__dict__.copy()

        # Apply updates
        for key, value in changes.items():
            setattr(db_user_department, key, value)

        db_user_department.updated_at = datetime.now(timezone.utc)
        db.add(db_user_department)
        await db.commit()
        await db.refresh(db_user_department)

        # Invalidate caches
        await invalidate_cache_prefix("user_department")
        await invalidate_cache_prefix(f"user:{db_user_department.user_id}")
        await invalidate_cache_prefix(f"department:{db_user_department.department_id}")
        if old_user_id != db_user_department.user_id:
            await invalidate_cache_prefix(f"user:{old_user_id}")
        if old_department_id != db_user_department.department_id:
            await invalidate_cache_prefix(f"department:{old_department_id}")
        logger.info(
            f"Cache invalidated for user_department, user:{db_user_department.user_id},{old_user_id}, department:{db_user_department.department_id},{old_department_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_USER_DEPARTMENT,
            table_affected="user_departments",
            record_id=user_department_id,
            old_values=old_values,
            new_values=db_user_department.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"User department updated: user_department_id={user_department_id}, user_id={db_user_department.user_id}, department_id={db_user_department.department_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return UserDepartmentOut.model_validate(db_user_department)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserDepartmentNotFoundError as e:
        logger.error(f"User department not found: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DepartmentNotFoundError as e:
        logger.error(f"Department not found: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ResourceConflictError as e:
        logger.error(f"Resource conflict: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error updating user department {user_department_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except DatabaseError as e:
        logger.error(f"Database error updating user department {user_department_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error updating user department {user_department_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def delete_user_department(
    user_department_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.DELETE_USER_DEPARTMENT]))
) -> None:
    """Soft delete a user-department assignment with validation, logging, and cache clearing."""
    try:
        if user_department_id <= 0:
            raise ValidationError(detail="Invalid user-department ID")

        query = select(UserDepartments).where(
            UserDepartments.user_department_id == user_department_id,
            UserDepartments.is_active.is_(True),
            UserDepartments.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_user_department = result.scalar_one_or_none()

        if not db_user_department:
            raise UserDepartmentNotFoundError(user_department_id=user_department_id)

        # Authorization check
        if not await _check_user_authorization(
            db, current_user, db_user_department.user_id, [Permission.DELETE_USER_DEPARTMENT, Permission.MANAGE_EMPLOYEES], request_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this user's department assignment"
            )

        # Prevent deletion of user's last department assignment if it's primary
        if db_user_department.is_primary:
            query = select(UserDepartments).where(
                UserDepartments.user_id == db_user_department.user_id,
                UserDepartments.is_active.is_(True),
                UserDepartments.deleted_at.is_(None)
            )
            result = await db.execute(query)
            user_departments = result.scalars().all()
            if len(user_departments) <= 1:
                raise ValidationError(detail="Cannot delete user's last primary department assignment")

        # Store old values for logging
        old_values = db_user_department.__dict__.copy()

        db_user_department.is_active = False
        db_user_department.deleted_at = datetime.now(timezone.utc)
        db.add(db_user_department)
        await db.commit()

        # Invalidate caches
        await invalidate_cache_prefix("user_department")
        await invalidate_cache_prefix(f"user:{db_user_department.user_id}")
        await invalidate_cache_prefix(f"department:{db_user_department.department_id}")
        logger.info(
            f"Cache invalidated for user_department, user:{db_user_department.user_id}, department:{db_user_department.department_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_USER_DEPARTMENT,
            table_affected="user_departments",
            record_id=user_department_id,
            old_values=old_values,
            new_values=None,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"User department soft deleted: user_department_id={user_department_id}, user_id={db_user_department.user_id}, department_id={db_user_department.department_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserDepartmentNotFoundError as e:
        logger.error(f"User department not found: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error deleting user department {user_department_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except DatabaseError as e:
        logger.error(f"Database error deleting user department {user_department_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error deleting user department {user_department_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_user_departments(
    user_id: int,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_USER_DEPARTMENT]))
) -> List[UserDepartmentOut]:
    """Retrieve a list of department assignments for a user with pagination."""
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user ID")
        await validate_user_exists(db, user_id, request_id)

        # Authorization check
        if not await _check_user_authorization(
            db, current_user, user_id, [Permission.VIEW_USER_DEPARTMENT, Permission.MANAGE_EMPLOYEES], request_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view department assignments for this user"
            )

        limit = limit or settings.DEFAULT_PAGE_SIZE
        cache_key = f"user_departments:{user_id}:{skip}:{limit}"
        cached_user_departments = await get_cache(cache_key)
        if cached_user_departments:
            logger.info(
                f"Cache hit for user_departments, user_id: {user_id}",
                extra={"request_id": request_id, "user_id": current_user.user_id}
            )
            return [UserDepartmentOut(**ud) for ud in cached_user_departments]

        query = select(UserDepartments).where(
            UserDepartments.user_id == user_id,
            UserDepartments.is_active.is_(True),
            UserDepartments.deleted_at.is_(None)
        ).order_by(UserDepartments.is_primary.desc(), UserDepartments.assigned_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        user_departments = result.scalars().all()

        user_departments_dict = [UserDepartmentOut.model_validate(ud).model_dump() for ud in user_departments]
        await set_cache(cache_key, user_departments_dict, ttl=300)
        logger.info(
            f"Cache set for user_departments, user_id: {user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

        logger.info(
            f"Retrieved {len(user_departments)} departments for user_id: {user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [UserDepartmentOut.model_validate(ud) for ud in user_departments]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error retrieving departments for user_id {user_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except DatabaseError as e:
        logger.error(f"Database error retrieving departments for user_id {user_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving departments for user_id {user_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def _assignment_exists(
    db: AsyncSession,
    user_id: int,
    department_id: int,
    exclude_id: Optional[int] = None,
    request_id: Optional[str] = None
) -> bool:
    """Check if a user is already assigned to a department."""
    try:
        query = select(UserDepartments).where(
            UserDepartments.user_id == user_id,
            UserDepartments.department_id == department_id,
            UserDepartments.is_active.is_(True),
            UserDepartments.deleted_at.is_(None)
        )
        if exclude_id:
            query = query.where(UserDepartments.user_department_id != exclude_id)

        result = await db.execute(query)
        exists = result.scalar_one_or_none() is not None
        logger.debug(
            f"Checked assignment existence: user_id={user_id}, department_id={department_id}, exists={exists}",
            extra={"request_id": request_id}
        )
        return exists
    except DatabaseError as e:
        logger.error(
            f"Database error checking assignment existence for user_id={user_id}, department_id={department_id}: {str(e)}",
            extra={"request_id": request_id}
        )
        raise

async def _clear_existing_primary(
    db: AsyncSession,
    user_id: int,
    exclude_id: Optional[int] = None,
    request_id: Optional[str] = None
) -> None:
    """Clear existing primary department assignments for a user."""
    try:
        query = select(UserDepartments).where(
            UserDepartments.user_id == user_id,
            UserDepartments.is_primary.is_(True),
            UserDepartments.is_active.is_(True),
            UserDepartments.deleted_at.is_(None)
        )
        if exclude_id:
            query = query.where(UserDepartments.user_department_id != exclude_id)

        result = await db.execute(query)
        existing_primary = result.scalars().all()

        for assignment in existing_primary:
            assignment.is_primary = False
            assignment.updated_at = datetime.now(timezone.utc)
            db.add(assignment)
        await db.commit()
        logger.debug(
            f"Cleared {len(existing_primary)} primary assignments for user_id={user_id}",
            extra={"request_id": request_id}
        )
    except DatabaseError as e:
        logger.error(
            f"Database error clearing primary assignments for user_id={user_id}: {str(e)}",
            extra={"request_id": request_id}
        )
        raise