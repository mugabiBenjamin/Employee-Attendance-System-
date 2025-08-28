from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.models.users import Users
from app.schemas.user_role import UserRoleCreate, UserRoleUpdate, UserRoleOut
from app.core.enums import SystemAction, Permission
from app.core.exceptions import UserRoleNotFoundError, ValidationError, DatabaseError, ResourceConflictError, UserNotFoundError, RoleNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions_dependency, invalidate_user_cache, invalidate_role_cache, get_user_permissions
from app.services.system_log_service import create_system_log
from app.schemas.system_log import SystemLogCreate
from app.core.validators import validate_user_exists, validate_role_exists
from app.core.config import Settings, get_settings
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
import logging

logger = logging.getLogger(__name__)

async def create_user_role(
    user_role: UserRoleCreate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _= Depends(require_permissions_dependency([Permission.CREATE_USER_ROLE]))
) -> UserRoleOut:
    """Assign a role to a user with validation, logging, and cache clearing."""
    try:
        # Validate user, role, and assigned_by
        await validate_user_exists(db, user_role.user_id, request_id)
        await validate_role_exists(db, user_role.role_id, request_id)
        if user_role.assigned_by:
            await validate_user_exists(db, user_role.assigned_by, request_id)

        # Check for existing assignment
        query = select(UserRoles).where(
            UserRoles.user_id == user_role.user_id,
            UserRoles.role_id == user_role.role_id,
            UserRoles.is_active.is_(True),
            UserRoles.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ResourceConflictError(detail="User is already assigned to this role")

        # Create user-role assignment
        db_user_role = UserRoles(
            user_id=user_role.user_id,
            role_id=user_role.role_id,
            assigned_by=user_role.assigned_by or current_user.user_id,
            is_active=user_role.is_active,
            assigned_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_user_role)
        await db.commit()
        await db.refresh(db_user_role)

        # Invalidate caches
        await invalidate_cache_prefix("user_role")
        await invalidate_cache_prefix(f"user:{user_role.user_id}")
        invalidate_user_cache(user_role.user_id)
        invalidate_role_cache(user_role.role_id)
        invalidate_user_cache(current_user.user_id)  # Invalidate current user's cache for permission updates
        logger.info(f"Cache invalidated for user_role, user:{user_role.user_id}, role:{user_role.role_id}, current_user:{current_user.user_id}", extra={"request_id": request_id})

        # Log action using SystemAction.INSERT
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="user_roles",
            record_id=db_user_role.user_role_id,
            old_values=None,
            new_values=db_user_role.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"User role assignment created, user_role_id: {db_user_role.user_role_id}, user_id: {user_role.user_id}, role_id: {user_role.role_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return UserRoleOut.model_validate(db_user_role)

    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RoleNotFoundError as e:
        logger.error(f"Role not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ResourceConflictError as e:
        logger.error(f"Resource conflict: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error creating user role: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error creating user role: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def read_user_role(
    user_role_id: int,
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _= Depends(require_permissions_dependency([Permission.VIEW_USER_ROLE]))
) -> UserRoleOut:
    """Retrieve a user-role assignment by ID."""
    try:
        if user_role_id <= 0:
            raise ValidationError(detail="Invalid user role ID")

        cache_key = f"user_role:{user_role_id}"
        cached_user_role = await get_cache(cache_key)
        if cached_user_role:
            logger.info(f"Cache hit for user_role_id: {user_role_id}", extra={"request_id": request_id})
            return UserRoleOut(**cached_user_role)

        query = select(UserRoles).where(
            UserRoles.user_role_id == user_role_id,
            UserRoles.is_active.is_(True),
            UserRoles.deleted_at.is_(None)
        )
        result = await db.execute(query)
        user_role = result.scalar_one_or_none()

        if not user_role:
            raise UserRoleNotFoundError(user_role_id=user_role_id)

        user_role_out = UserRoleOut.model_validate(user_role)
        user_role_dict = user_role_out.model_dump(mode='json')
        await set_cache(cache_key, user_role_dict, ttl=300)
        logger.info(f"Cache set for user_role_id: {user_role_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved user role, user_role_id: {user_role_id}",
            extra={"request_id": request_id}
        )
        return user_role_out

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserRoleNotFoundError as e:
        logger.error(f"User role not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving user role {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving user role {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def read_user_roles(
    user_id: Optional[int] = None,
    role_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _= Depends(require_permissions_dependency([Permission.VIEW_USER_ROLE]))
) -> List[UserRoleOut]:
    """Retrieve a list of user-role assignments with optional filters and pagination."""
    try:
        if skip < 0 or (limit is not None and limit < 0):
            raise ValidationError(detail="Invalid pagination parameters")

        limit = limit or settings.DEFAULT_PAGE_SIZE
        cache_key = f"user_roles:{user_id or 'all'}:{role_id or 'all'}:{skip}:{limit}"
        cached_user_roles = await get_cache(cache_key)
        if cached_user_roles:
            logger.info(f"Cache hit for user_roles, user_id: {user_id or 'all'}, role_id: {role_id or 'all'}", extra={"request_id": request_id})
            return [UserRoleOut(**ur) for ur in cached_user_roles]

        query = select(UserRoles).where(
            UserRoles.is_active.is_(True),
            UserRoles.deleted_at.is_(None)
        )

        if user_id:
            await validate_user_exists(db, user_id, request_id)
            query = query.where(UserRoles.user_id == user_id)

        if role_id:
            await validate_role_exists(db, role_id, request_id)
            query = query.where(UserRoles.role_id == role_id)

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        user_roles = result.scalars().all()

        user_roles_out = [UserRoleOut.model_validate(ur) for ur in user_roles]
        user_roles_dict = [ur.model_dump(mode='json') for ur in user_roles_out]
        await set_cache(cache_key, user_roles_dict, ttl=300)
        logger.info(f"Cache set for user_roles, user_id: {user_id or 'all'}, role_id: {role_id or 'all'}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(user_roles)} user roles",
            extra={"request_id": request_id, "user_id": user_id, "role_id": role_id}
        )
        return user_roles_out

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RoleNotFoundError as e:
        logger.error(f"Role not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving user roles: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving user roles: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def update_user_role(
    user_role_id: int,
    user_role_update: UserRoleUpdate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _= Depends(require_permissions_dependency([Permission.UPDATE_USER_ROLE]))
) -> UserRoleOut:
    """Update a user-role assignment with validation, logging, and cache clearing."""
    try:
        if user_role_id <= 0:
            raise ValidationError(detail="Invalid user role ID")

        # Retrieve user-role assignment
        query = select(UserRoles).where(
            UserRoles.user_role_id == user_role_id,
            UserRoles.is_active.is_(True),
            UserRoles.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_user_role = result.scalar_one_or_none()

        if not db_user_role:
            raise UserRoleNotFoundError(user_role_id=user_role_id)

        # Validate update data
        update_data = user_role_update.model_dump(exclude_none=True)
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        # Validate user, role, and assigned_by if updated
        if "user_id" in update_data:
            await validate_user_exists(db, update_data["user_id"], request_id)
        if "role_id" in update_data:
            await validate_role_exists(db, update_data["role_id"], request_id)
        if "assigned_by" in update_data and update_data["assigned_by"]:
            await validate_user_exists(db, update_data["assigned_by"], request_id)

        # Check for existing assignment
        if "user_id" in update_data or "role_id" in update_data:
            query = select(UserRoles).where(
                UserRoles.user_id == (update_data.get("user_id", db_user_role.user_id)),
                UserRoles.role_id == (update_data.get("role_id", db_user_role.role_id)),
                UserRoles.user_role_id != user_role_id,
                UserRoles.is_active.is_(True),
                UserRoles.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise ResourceConflictError(detail="User is already assigned to this role")

        # Store old values for logging
        old_values = db_user_role.__dict__.copy()

        # Apply updates
        for key, value in update_data.items():
            setattr(db_user_role, key, value)

        db_user_role.updated_at = datetime.now(timezone.utc)
        db.add(db_user_role)
        await db.commit()
        await db.refresh(db_user_role)

        # Invalidate caches
        await invalidate_cache_prefix("user_role")
        await invalidate_cache_prefix(f"user:{db_user_role.user_id}")
        invalidate_user_cache(db_user_role.user_id)
        invalidate_role_cache(db_user_role.role_id)
        invalidate_user_cache(current_user.user_id)  # Invalidate current user's cache for permission updates
        logger.info(f"Cache invalidated for user_role, user:{db_user_role.user_id}, role:{db_user_role.role_id}, current_user:{current_user.user_id}", extra={"request_id": request_id})

        # Log action using SystemAction.UPDATE
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE,
            table_affected="user_roles",
            record_id=user_role_id,
            old_values=old_values,
            new_values=db_user_role.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"User role updated, user_role_id: {user_role_id}, user_id: {db_user_role.user_id}, role_id: {db_user_role.role_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return UserRoleOut.model_validate(db_user_role)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserRoleNotFoundError as e:
        logger.error(f"User role not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RoleNotFoundError as e:
        logger.error(f"Role not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ResourceConflictError as e:
        logger.error(f"Resource conflict: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error updating user role {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error updating user role {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def delete_user_role(
    user_role_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _= Depends(require_permissions_dependency([Permission.DELETE_USER_ROLE]))
) -> None:
    """Soft delete a user-role assignment with validation, logging, and cache clearing."""
    try:
        if user_role_id <= 0:
            raise ValidationError(detail="Invalid user role ID")

        query = select(UserRoles).where(
            UserRoles.user_role_id == user_role_id,
            UserRoles.is_active.is_(True),
            UserRoles.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_user_role = result.scalar_one_or_none()

        if not db_user_role:
            raise UserRoleNotFoundError(user_role_id=user_role_id)

        # Prevent deletion of user's last role assignment
        query = select(UserRoles).where(
            UserRoles.user_id == db_user_role.user_id,
            UserRoles.is_active.is_(True),
            UserRoles.deleted_at.is_(None)
        )
        result = await db.execute(query)
        user_roles = result.scalars().all()

        if len(user_roles) <= 1:
            raise ValidationError(detail="Cannot delete user's last role assignment")

        db_user_role.is_active = False
        db_user_role.deleted_at = datetime.now(timezone.utc)
        db.add(db_user_role)
        await db.commit()

        # Invalidate caches
        await invalidate_cache_prefix("user_role")
        await invalidate_cache_prefix(f"user:{db_user_role.user_id}")
        invalidate_user_cache(db_user_role.user_id)
        invalidate_role_cache(db_user_role.role_id)
        invalidate_user_cache(current_user.user_id)  # Invalidate current user's cache for permission updates
        logger.info(f"Cache invalidated for user_role, user:{db_user_role.user_id}, role:{db_user_role.role_id}, current_user:{current_user.user_id}", extra={"request_id": request_id})

        # Log action using SystemAction.DELETE
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE,
            table_affected="user_roles",
            record_id=user_role_id,
            old_values=db_user_role.__dict__,
            new_values=None,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"User role soft deleted, user_role_id: {user_role_id}, user_id: {db_user_role.user_id}, role_id: {db_user_role.role_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserRoleNotFoundError as e:
        logger.error(f"User role not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error deleting user role {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error deleting user role {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_user_roles(
    user_id: int,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _= Depends(require_permissions_dependency([Permission.VIEW_USER_ROLE]))
) -> List[UserRoleOut]:
    """Retrieve a list of role assignments for a user with pagination."""
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user ID")
        await validate_user_exists(db, user_id, request_id)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        cache_key = f"user_roles:{user_id}:{skip}:{limit}"
        cached_user_roles = await get_cache(cache_key)
        if cached_user_roles:
            logger.info(f"Cache hit for user_roles, user_id: {user_id}", extra={"request_id": request_id})
            return [UserRoleOut(**ur) for ur in cached_user_roles]

        query = select(UserRoles).where(
            UserRoles.user_id == user_id,
            UserRoles.is_active.is_(True),
            UserRoles.deleted_at.is_(None)
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        user_roles = result.scalars().all()

        user_roles_out = [UserRoleOut.model_validate(ur) for ur in user_roles]
        user_roles_dict = [ur.model_dump(mode='json') for ur in user_roles_out]
        await set_cache(cache_key, user_roles_dict, ttl=300)
        logger.info(f"Cache set for user_roles, user_id: {user_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(user_roles)} roles for user_id: {user_id}",
            extra={"request_id": request_id}
        )
        return user_roles_out

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving roles for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving roles for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_user_permissions(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _= Depends(require_permissions_dependency([Permission.VIEW_USER_ROLE]))
) -> dict:
    """Retrieve the permissions assigned to a user based on their roles."""
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user ID")
        await validate_user_exists(db, user_id, request_id)

        # Use get_user_permissions from permissions file
        permissions = await get_user_permissions(user_id, db)
        
        logger.info(
            f"Retrieved {len(permissions)} permissions for user_id: {user_id}",
            extra={"request_id": request_id}
        )
        return permissions

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving permissions for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving permissions for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")