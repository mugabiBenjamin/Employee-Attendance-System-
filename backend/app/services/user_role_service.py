from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.schemas.user_role import UserRoleCreate, UserRoleUpdate, UserRoleOut
from app.core.enums import SystemAction, Permission
from app.core.exceptions import UserRoleNotFoundError, ValidationError, DatabaseError, ResourceConflictError, UserNotFoundError, RoleNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.services.system_log_service import create_system_log
from app.schemas.system_log import SystemLogCreate
from app.core.validators import validate_user_exists, validate_role_exists
from app.core.config import Settings, get_settings
from app.models.users import Users
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

async def create_user_role(
    user_role: UserRoleCreate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.CREATE_USER_ROLE]))
) -> UserRoleOut:
    """
    Assign a role to a user with validation and logging."""
    try:
        # Validate user and role
        await validate_user_exists(db, user_role.user_id, request_id)
        await validate_role_exists(db, user_role.role_id, request_id)

        # Check for existing assignment
        query = select(UserRoles).where(
            UserRoles.user_id == user_role.user_id,
            UserRoles.role_id == user_role.role_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ResourceConflictError(detail="User is already assigned to this role")

        # Create user-role assignment
        db_user_role = UserRoles(
            user_id=user_role.user_id,
            role_id=user_role.role_id,
            assigned_by=current_user.user_id,
            is_active=user_role.is_active,
            assigned_at=datetime.now(timezone.utc),
            deleted_at=None
        )
        db.add(db_user_role)
        await db.commit()
        await db.refresh(db_user_role)

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="user_roles",
            record_id=db_user_role.user_role_id,
            old_values=None,
            new_values=db_user_role.__dict__,
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"User role assignment created, user_role_id: {db_user_role.user_role_id}, user_id: {user_role.user_id}",
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
        logger.error(f"Database error creating user role assignment: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error creating user role assignment: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def read_user_role(
    user_role_id: int,
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_USER_ROLE]))
) -> UserRoleOut:
    """
    Retrieve a user-role assignment by ID."""
    try:
        query = select(UserRoles).where(
            UserRoles.user_role_id == user_role_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        )
        result = await db.execute(query)
        user_role = result.scalar_one_or_none()

        if not user_role:
            raise UserRoleNotFoundError(user_role_id=user_role_id)

        logger.info(
            f"Retrieved user role assignment, user_role_id: {user_role_id}",
            extra={"request_id": request_id}
        )
        return UserRoleOut.model_validate(user_role)

    except UserRoleNotFoundError as e:
        logger.error(f"User role not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving user role assignment {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving user role assignment {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def read_user_roles(
    user_id: Optional[int] = None,
    role_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_USER_ROLE]))
) -> List[UserRoleOut]:
    """
    Retrieve a list of user-role assignments with optional filters and pagination."""
    try:
        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = select(UserRoles).where(
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
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

        logger.info(
            f"Retrieved {len(user_roles)} user role assignments",
            extra={"request_id": request_id, "user_id": user_id, "role_id": role_id}
        )
        return [UserRoleOut.model_validate(ur) for ur in user_roles]

    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RoleNotFoundError as e:
        logger.error(f"Role not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving user role assignments: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving user role assignments: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def update_user_role(
    user_role_id: int,
    user_role_update: UserRoleUpdate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.UPDATE_USER_ROLE]))
) -> UserRoleOut:
    """
    Update a user-role assignment with validation and logging."""
    try:
        # Retrieve user-role assignment
        query = select(UserRoles).where(
            UserRoles.user_role_id == user_role_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        )
        result = await db.execute(query)
        db_user_role = result.scalar_one_or_none()

        if not db_user_role:
            raise UserRoleNotFoundError(user_role_id=user_role_id)

        # Validate update data
        update_data = user_role_update.model_dump(exclude_none=True)
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        # Validate user if updated
        if "user_id" in update_data:
            await validate_user_exists(db, update_data["user_id"], request_id)

        # Validate role if updated
        if "role_id" in update_data:
            await validate_role_exists(db, update_data["role_id"], request_id)

            # Check for existing assignment
            query = select(UserRoles).where(
                UserRoles.user_id == (update_data.get("user_id", db_user_role.user_id)),
                UserRoles.role_id == update_data["role_id"],
                UserRoles.user_role_id != user_role_id,
                UserRoles.is_active == True,
                UserRoles.deleted_at == None
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

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE,
            table_affected="user_roles",
            record_id=user_role_id,
            old_values=old_values,
            new_values=db_user_role.__dict__,
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"User role assignment updated, user_role_id: {user_role_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return UserRoleOut.model_validate(db_user_role)

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
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error updating user role assignment {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error updating user role assignment {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def delete_user_role(
    user_role_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.DELETE_USER_ROLE]))
) -> None:
    """
    Soft delete a user-role assignment with validation and logging."""
    try:
        query = select(UserRoles).where(
            UserRoles.user_role_id == user_role_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        )
        result = await db.execute(query)
        db_user_role = result.scalar_one_or_none()

        if not db_user_role:
            raise UserRoleNotFoundError(user_role_id=user_role_id)

        # Prevent deletion of user's last role assignment
        query = select(UserRoles).where(
            UserRoles.user_id == db_user_role.user_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        )
        result = await db.execute(query)
        user_roles = result.scalars().all()
        
        if len(user_roles) <= 1:
            raise ValidationError(detail="Cannot delete user's last role assignment")

        db_user_role.is_active = False
        db_user_role.deleted_at = datetime.now(timezone.utc)
        db.add(db_user_role)
        await db.commit()

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE,
            table_affected="user_roles",
            record_id=user_role_id,
            old_values=db_user_role.__dict__,
            new_values=None,
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"User role assignment soft deleted, user_role_id: {user_role_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except UserRoleNotFoundError as e:
        logger.error(f"User role not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error deleting user role assignment {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error deleting user role assignment {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_user_roles(
    user_id: int,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_USER_ROLE]))
) -> List[UserRoleOut]:
    """
    Retrieve a list of role assignments for a user with pagination."""
    try:
        await validate_user_exists(db, user_id, request_id)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = select(UserRoles).where(
            UserRoles.user_id == user_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        user_roles = result.scalars().all()

        logger.info(
            f"Retrieved {len(user_roles)} role assignments for user_id: {user_id}",
            extra={"request_id": request_id}
        )
        return [UserRoleOut.model_validate(ur) for ur in user_roles]

    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving role assignments for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving role assignments for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_user_permissions(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None
) -> List[Permission]:
    """
    Retrieve the permissions assigned to a user based on their roles."""
    try:
        await validate_user_exists(db, user_id, request_id)

        # Get user roles
        query = select(UserRoles).where(
            UserRoles.user_id == user_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        )
        result = await db.execute(query)
        user_roles = result.scalars().all()

        if not user_roles:
            logger.info(
                f"No roles found for user_id: {user_id}",
                extra={"request_id": request_id}
            )
            return []

        # Get permissions from roles
        role_ids = [ur.role_id for ur in user_roles]
        query = select(Roles).where(
            Roles.role_id.in_(role_ids),
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        roles = result.scalars().all()

        # Aggregate permissions
        permissions = set()
        for role in roles:
            if role.permissions:  # Assume permissions is a list of Permission enums
                permissions.update(role.permissions)

        logger.info(
            f"Retrieved {len(permissions)} permissions for user_id: {user_id}",
            extra={"request_id": request_id}
        )
        return list(permissions)

    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving permissions for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving permissions for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")