from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.user_roles import UserRoles
from app.schemas.user_role import UserRoleCreate, UserRoleUpdate, UserRoleOut
from app.core.enums import SystemAction, Permission
from app.core.exceptions import ResourceNotFoundError, ValidationError, DatabaseError, ResourceConflictError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.services.system_log_service import SystemLogService, get_system_log_service
from app.schemas.system_log import SystemLogCreate
from app.core.validators import validate_user_exists, validate_role_exists
from app.core.config import Settings, get_settings
from app.models.users import Users
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

async def create_user_role(
    user_role: UserRoleCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    log_service: SystemLogService = Depends(get_system_log_service),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.CREATE_USER_ROLE]))
) -> UserRoleOut:
    """
    Assign a role to a user with validation and logging. Requires CREATE_USER_ROLE permission.
    """
    try:
        # Validate user and role
        await validate_user_exists(db, user_role.user_id)
        await validate_role_exists(db, user_role.role_id)

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
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent")
        )
        await log_service.create_system_log(log, current_user, request)

        logger.info(f"User role assignment created, user_role_id: {db_user_role.user_role_id}, user_id: {user_role.user_id}")
        return UserRoleOut.model_validate(db_user_role)

    except HTTPException:
        raise
    except DatabaseError as e:
        logger.error(f"Database error creating user role assignment for user_id {user_role.user_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating user role assignment for user_id {user_role.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating user role assignment"
        )

async def get_user_role_by_id(
    user_role_id: int,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_USER_ROLE]))
) -> Optional[UserRoleOut]:
    """
    Retrieve a user-role assignment by ID. Requires VIEW_USER_ROLE permission.
    """
    try:
        query = select(UserRoles).where(
            UserRoles.user_role_id == user_role_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        )
        result = await db.execute(query)
        user_role = result.scalar_one_or_none()

        if not user_role:
            raise ResourceNotFoundError(resource="User role assignment", identifier=f"ID {user_role_id}")

        return UserRoleOut.model_validate(user_role)

    except ResourceNotFoundError:
        raise
    except DatabaseError as e:
        logger.error(f"Database error retrieving user role assignment {user_role_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving user role assignment {user_role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving user role assignment"
        )

async def get_user_roles(
    user_id: int,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_USER_ROLE]))
) -> List[UserRoleOut]:
    """
    Retrieve a list of role assignments for a user with pagination. Requires VIEW_USER_ROLE permission.
    """
    try:
        await validate_user_exists(db, user_id)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = select(UserRoles).where(
            UserRoles.user_id == user_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        user_roles = result.scalars().all()

        logger.info(f"Retrieved {len(user_roles)} role assignments for user_id: {user_id}")
        return [UserRoleOut.model_validate(ur) for ur in user_roles]

    except ResourceNotFoundError:
        raise
    except DatabaseError as e:
        logger.error(f"Database error retrieving role assignments for user_id {user_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving role assignments for user_id {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving role assignments"
        )

async def update_user_role(
    user_role_id: int,
    user_role_update: UserRoleUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    log_service: SystemLogService = Depends(get_system_log_service),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.UPDATE_USER_ROLE]))
) -> UserRoleOut:
    """
    Update a user-role assignment with validation and logging. Requires UPDATE_USER_ROLE permission.
    """
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
            raise ResourceNotFoundError(resource="User role assignment", identifier=f"ID {user_role_id}")

        # Validate user if updated
        update_data = user_role_update.model_dump(exclude_none=True)
        if "user_id" in update_data:
            await validate_user_exists(db, update_data["user_id"])

        # Validate role if updated
        if "role_id" in update_data:
            await validate_role_exists(db, update_data["role_id"])

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
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent")
        )
        await log_service.create_system_log(log, current_user, request)

        logger.info(f"User role assignment updated, user_role_id: {user_role_id}")
        return UserRoleOut.model_validate(db_user_role)

    except HTTPException:
        raise
    except DatabaseError as e:
        logger.error(f"Database error updating user role assignment {user_role_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating user role assignment {user_role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating user role assignment"
        )

async def delete_user_role(
    user_role_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    log_service: SystemLogService = Depends(get_system_log_service),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.DELETE_USER_ROLE]))
) -> None:
    """
    Soft delete a user-role assignment with logging. Requires DELETE_USER_ROLE permission.
    """
    try:
        query = select(UserRoles).where(
            UserRoles.user_role_id == user_role_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        )
        result = await db.execute(query)
        db_user_role = result.scalar_one_or_none()

        if not db_user_role:
            raise ResourceNotFoundError(resource="User role assignment", identifier=f"ID {user_role_id}")

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
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent")
        )
        await log_service.create_system_log(log, current_user, request)

        logger.info(f"User role assignment soft deleted, user_role_id: {user_role_id}")

    except HTTPException:
        raise
    except DatabaseError as e:
        logger.error(f"Database error deleting user role assignment {user_role_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting user role assignment {user_role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting user role assignment"
        )