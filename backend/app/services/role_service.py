from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.roles import Roles
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.schemas.role import RoleCreate, RoleUpdate, RoleOut
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import ResourceNotFoundError, ValidationError, DatabaseError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db
from cachetools import TTLCache
import logging

logger = logging.getLogger(__name__)

# External reference to permission cache
externals = {"permission_cache": TTLCache(maxsize=1000, ttl=300), "role_permission_cache": TTLCache(maxsize=100, ttl=300)}

async def create_role(
    role: RoleCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.CREATE_ROLE]))
) -> RoleOut:
    """
    Create a new role with validation and logging.
    """
    try:
        # Validate role_name
        valid_roles = ['Employee', 'Manager', 'HR', 'Admin', 'Super_Admin']
        if role.role_name not in valid_roles:
            raise ValidationError(detail=f"Invalid role name. Must be one of: {', '.join(valid_roles)}")

        # Check for existing role
        query = select(Roles).where(
            Roles.role_name == role.role_name,
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ValidationError(detail="Role name already exists")

        # Validate permissions
        invalid_permissions = [p for p in role.permissions.keys() if p not in [perm.value for perm in Permission]]
        if invalid_permissions:
            raise ValidationError(detail=f"Invalid permissions: {', '.join(invalid_permissions)}")

        # Create role
        db_role = Roles(
            role_name=role.role_name,
            description=role.description,
            permissions=role.permissions,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_role)
        await db.commit()
        await db.refresh(db_role)

        # Clear role permission cache
        externals["role_permission_cache"].clear()
        logger.debug("Role permission cache cleared after role creation")

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="roles",
            record_id=db_role.role_id,
            old_values=None,
            new_values=db_role.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Role created, role_id: {db_role.role_id}, role_name: {db_role.role_name}")
        return RoleOut.model_validate(db_role)

    except HTTPException:
        raise
    except DatabaseError as e:
        logger.error(f"Database error creating role: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating role: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating role"
        )

async def get_role_by_id(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.VIEW_ROLE]))
) -> Optional[RoleOut]:
    """
    Retrieve a role by ID.
    """
    try:
        query = select(Roles).where(
            Roles.role_id == role_id,
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        role = result.scalar_one_or_none()

        if not role:
            raise ResourceNotFoundError(resource="Role", identifier=f"ID {role_id}")

        return RoleOut.model_validate(role)

    except ResourceNotFoundError:
        raise
    except DatabaseError as e:
        logger.error(f"Database error retrieving role {role_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving role"
        )

async def get_roles(
    skip: int = 0,
    limit: int = 50,  # Default value as fallback
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),  # Inject Settings
    _: bool = Depends(require_permissions([Permission.VIEW_ROLE]))
) -> List[RoleOut]:
    """
    Retrieve a list of active roles with pagination.
    """
    try:
        query = select(Roles).where(
            Roles.is_active == True,
            Roles.deleted_at == None
        ).offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)  # Use injected settings
        result = await db.execute(query)
        roles = result.scalars().all()

        logger.info(f"Retrieved {len(roles)} roles")
        return [RoleOut.model_validate(role) for role in roles]

    except DatabaseError as e:
        logger.error(f"Database error retrieving roles: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving roles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving roles"
        )

async def update_role(
    role_id: int,
    role_update: RoleUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.UPDATE_ROLE]))
) -> RoleOut:
    """
    Update a role with validation and logging.
    """
    try:
        # Retrieve role
        query = select(Roles).where(
            Roles.role_id == role_id,
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        db_role = result.scalar_one_or_none()

        if not db_role:
            raise ResourceNotFoundError(resource="Role", identifier=f"ID {role_id}")

        # Check for duplicate role name if updated
        update_data = role_update.model_dump(exclude_none=True)
        if "role_name" in update_data:
            valid_roles = ['Employee', 'Manager', 'HR', 'Admin', 'Super_Admin']
            if update_data["role_name"] not in valid_roles:
                raise ValidationError(detail=f"Invalid role name. Must be one of: {', '.join(valid_roles)}")
            query = select(Roles).where(
                Roles.role_name == update_data["role_name"],
                Roles.role_id != role_id,
                Roles.is_active == True,
                Roles.deleted_at == None
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise ValidationError(detail="Role name already exists")

        # Validate permissions if updated
        if "permissions" in update_data:
            invalid_permissions = [p for p in update_data["permissions"].keys() if p not in [perm.value for perm in Permission]]
            if invalid_permissions:
                raise ValidationError(detail=f"Invalid permissions: {', '.join(invalid_permissions)}")

        # Store old values for logging
        old_values = db_role.__dict__.copy()

        # Apply updates
        for key, value in update_data.items():
            setattr(db_role, key, value)

        db_role.updated_at = datetime.now(timezone.utc)
        db.add(db_role)
        await db.commit()
        await db.refresh(db_role)

        # Clear role permission cache
        externals["role_permission_cache"].clear()
        logger.debug("Role permission cache cleared after role update")

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE,
            table_affected="roles",
            record_id=role_id,
            old_values=old_values,
            new_values=db_role.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Role updated, role_id: {role_id}")
        return RoleOut.model_validate(db_role)

    except HTTPException:
        raise
    except DatabaseError as e:
        logger.error(f"Database error updating role {role_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating role"
        )

async def delete_role(
    role_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.DELETE_ROLE]))
) -> None:
    """
    Soft delete a role with logging.
    """
    try:
        query = select(Roles).where(
            Roles.role_id == role_id,
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        db_role = result.scalar_one_or_none()

        if not db_role:
            raise ResourceNotFoundError(resource="Role", identifier=f"ID {role_id}")

        db_role.is_active = False
        db_role.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        # Clear role permission cache
        externals["role_permission_cache"].clear()
        logger.debug("Role permission cache cleared after role deletion")

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.DELETE,
            table_affected="roles",
            record_id=role_id,
            old_values=db_role.__dict__,
            new_values=None,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Role soft deleted, role_id: {role_id}")

    except ResourceNotFoundError:
        raise
    except DatabaseError as e:
        logger.error(f"Database error deleting role {role_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting role"
        )