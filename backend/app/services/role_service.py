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
from app.core.exceptions import RoleNotFoundError, ValidationError, BusinessLogicError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_role_not_assigned
import logging

logger = logging.getLogger(__name__)

async def create_role(
    role: RoleCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.CREATE_ROLE]))
) -> RoleOut:
    """Create a new role with validation, logging, and cache clearing."""
    try:
        query = select(Roles).where(
            Roles.role_name == role.role_name,
            Roles.is_active.is_(True),
            Roles.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ValidationError(detail="Role name already exists")

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

        await invalidate_cache_prefix("role")
        logger.debug(f"Role cache cleared after role creation: {db_role.role_name}")

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_ROLE,
            table_affected="roles",
            record_id=db_role.role_id,
            old_values=None,
            new_values=db_role.__dict__,
            ip_address=str(request.client.host),
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
        cache_key = f"role:{role_id}"
        cached_role = await get_cache(cache_key)
        if cached_role:
            return RoleOut(**cached_role)

        query = select(Roles).where(
            Roles.role_id == role_id,
            Roles.is_active.is_(True),
            Roles.deleted_at.is_(None)
        )
        result = await db.execute(query)
        role = result.scalar_one_or_none()

        if not role:
            raise RoleNotFoundError(role_id=role_id)

        role_dict = RoleOut.model_validate(role).model_dump()
        await set_cache(cache_key, role_dict, ttl=300)

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
    limit: int = 0,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_ROLE]))
) -> List[RoleOut]:
    """Retrieve a list of active roles with pagination."""
    try:
        if skip < 0 or limit < 0:
            raise ValidationError(detail="Invalid pagination parameters")

        limit = limit or settings.DEFAULT_PAGE_SIZE
        cache_key = f"roles:{skip}:{limit}"
        cached_roles = await get_cache(cache_key)
        if cached_roles:
            return [RoleOut(**role) for role in cached_roles]

        query = select(Roles).where(
            Roles.is_active.is_(True),
            Roles.deleted_at.is_(None)
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        roles = result.scalars().all()

        roles_dict = [RoleOut.model_validate(role).model_dump() for role in roles]
        await set_cache(cache_key, roles_dict, ttl=300)

        logger.info(f"Retrieved {len(roles)} roles for user_id: {current_user.user_id}")
        return [RoleOut.model_validate(role) for role in roles]

    except ValidationError:
        raise
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
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        if "role_name" in update_data:
            query = select(Roles).where(
                Roles.role_name == update_data["role_name"],
                Roles.role_id != role_id,
                Roles.is_active.is_(True),
                Roles.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise ValidationError(detail="Role name already exists")

        old_values = db_role.__dict__.copy()
        for key, value in update_data.items():
            setattr(db_role, key, value)
        db_role.updated_at = datetime.now(timezone.utc)
        db.add(db_role)
        await db.commit()
        await db.refresh(db_role)

        await invalidate_cache_prefix("role")
        logger.debug(f"Role cache cleared after role update: {db_role.role_name}")

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_ROLE,
            table_affected="roles",
            record_id=role_id,
            old_values=old_values,
            new_values=db_role.__dict__,
            ip_address=str(request.client.host),
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
    """Soft delete a role with validation, logging, and cache clearing."""
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

        await validate_role_not_assigned(role_id, db)

        db_role.is_active = False
        db_role.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        await invalidate_cache_prefix("role")
        logger.debug(f"Role cache cleared after role deletion: {db_role.role_name}")

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_ROLE,
            table_affected="roles",
            record_id=role_id,
            old_values=db_role.__dict__,
            new_values=None,
            ip_address=str(request.client.host),
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Role soft deleted, role_id: {role_id}, role_name: {db_role.role_name}")

    except (RoleNotFoundError, BusinessLogicError):
        raise
    except Exception as e:
        logger.error(f"Error deleting role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting role"
        )