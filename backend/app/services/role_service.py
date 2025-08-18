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
from app.core.exceptions import RoleNotFoundError, ValidationError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db
from cachetools import TTLCache
import logging

logger = logging.getLogger(__name__)

externals = {"permission_cache": TTLCache(maxsize=1000, ttl=300), "role_permission_cache": TTLCache(maxsize=100, ttl=300)}

async def create_role(
    role: RoleCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.CREATE_ROLE]))
) -> RoleOut:
    """Create a new role with validation, logging, and cache clearing."""
    try:
        valid_roles = {'Employee', 'Manager', 'HR', 'Admin', 'Super_Admin'}
        if role.role_name not in valid_roles:
            raise ValidationError(detail=f"Invalid role name. Must be one of: {', '.join(sorted(valid_roles))}")

        query = select(Roles).where(
            Roles.role_name == role.role_name,
            Roles.is_active.is_(True),
            Roles.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ValidationError(detail="Role name already exists")

        invalid_permissions = [p for p in role.permissions.keys() if p not in {perm.value for perm in Permission}]
        if invalid_permissions:
            raise ValidationError(detail=f"Invalid permissions: {', '.join(invalid_permissions)}")

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

        externals["role_permission_cache"].clear()
        logger.debug(f"Role permission cache cleared after role creation: {db_role.role_name}")

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_ROLE,
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

    except (ValidationError, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error creating role: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating role"
        )

async def get_role(
    role_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.VIEW_ROLE]))
) -> RoleOut:
    """Retrieve a role by ID."""
    try:
        query = select(Roles).where(
            Roles.role_id == role_id,
            Roles.is_active.is_(True),
            Roles.deleted_at.is_(None)
        )
        result = await db.execute(query)
        role = result.scalar_one_or_none()

        if not role:
            raise RoleNotFoundError(role_id=role_id)

        logger.info(f"Retrieved role, role_id: {role_id}, user_id: {current_user.user_id}")
        return RoleOut.model_validate(role)

    except RoleNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error retrieving role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving role"
        )

async def list_roles(
    skip: int = 0,
    limit: int = 50,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_ROLE]))
) -> List[RoleOut]:
    """Retrieve a list of active roles with pagination."""
    try:
        query = select(Roles).where(
            Roles.is_active.is_(True),
            Roles.deleted_at.is_(None)
        ).offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        result = await db.execute(query)
        roles = result.scalars().all()

        logger.info(f"Retrieved {len(roles)} roles for user_id: {current_user.user_id}")
        return [RoleOut.model_validate(role) for role in roles]

    except Exception as e:
        logger.error(f"Error retrieving roles: {str(e)}")
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
    """Update a role with validation, logging, and cache clearing."""
    try:
        query = select(Roles).where(
            Roles.role_id == role_id,
            Roles.is_active.is_(True),
            Roles.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_role = result.scalar_one_or_none()

        if not db_role:
            raise RoleNotFoundError(role_id=role_id)

        update_data = role_update.model_dump(exclude_none=True)
        if "role_name" in update_data:
            valid_roles = {'Employee', 'Manager', 'HR', 'Admin', 'Super_Admin'}
            if update_data["role_name"] not in valid_roles:
                raise ValidationError(detail=f"Invalid role name. Must be one of: {', '.join(sorted(valid_roles))}")
            query = select(Roles).where(
                Roles.role_name == update_data["role_name"],
                Roles.role_id != role_id,
                Roles.is_active.is_(True),
                Roles.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise ValidationError(detail="Role name already exists")

        if "permissions" in update_data:
            invalid_permissions = [p for p in update_data["permissions"].keys() if p not in {perm.value for perm in Permission}]
            if invalid_permissions:
                raise ValidationError(detail=f"Invalid permissions: {', '.join(invalid_permissions)}")

        old_values = db_role.__dict__.copy()
        for key, value in update_data.items():
            setattr(db_role, key, value)
        db_role.updated_at = datetime.now(timezone.utc)
        db.add(db_role)
        await db.commit()
        await db.refresh(db_role)

        externals["role_permission_cache"].clear()
        logger.debug(f"Role permission cache cleared after role update: {db_role.role_name}")

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_ROLE,
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

        logger.info(f"Role updated, role_id: {role_id}, role_name: {db_role.role_name}")
        return RoleOut.model_validate(db_role)

    except (RoleNotFoundError, ValidationError, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error updating role {role_id}: {str(e)}")
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
    """Soft delete a role with logging and cache clearing."""
    try:
        query = select(Roles).where(
            Roles.role_id == role_id,
            Roles.is_active.is_(True),
            Roles.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_role = result.scalar_one_or_none()

        if not db_role:
            raise RoleNotFoundError(role_id=role_id)

        db_role.is_active = False
        db_role.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        externals["role_permission_cache"].clear()
        logger.debug(f"Role permission cache cleared after role deletion: {db_role.role_name}")

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_ROLE,
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

        logger.info(f"Role soft deleted, role_id: {role_id}, role_name: {db_role.role_name}")

    except RoleNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error deleting role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting role"
        )