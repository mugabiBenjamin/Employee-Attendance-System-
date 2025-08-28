from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.roles import Roles
from app.models.users import Users
from app.schemas.role import RoleCreate, RoleUpdate, RoleOut
from app.schemas.system_log import SystemLogCreate
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission, RoleName, validate_permissions_list
from app.core.exceptions import RoleNotFoundError, ValidationError, BusinessLogicError
from app.core.security import get_current_user
from app.core.permissions import require_permissions_dependency, invalidate_role_cache, invalidate_user_cache
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix, validate_enum_value
from app.core.validators import validate_role_not_assigned
from app.services.system_log_service import create_system_log
import logging

logger = logging.getLogger(__name__)

async def create_role(
    role: RoleCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _= Depends(require_permissions_dependency([Permission.CREATE_ROLE]))
) -> RoleOut:
    """Create a new role with validation, logging, and cache clearing."""
    try:
        # Validate role_name against RoleName enum
        if not await validate_enum_value(RoleName, role.role_name):
            raise ValidationError(detail=f"Invalid role name: {role.role_name}")

        # Validate permissions using permissions file function
        is_valid, invalid_perms = validate_permissions_list([k for k, v in role.permissions.items() if v])
        if not is_valid:
            raise ValidationError(detail=f"Invalid permissions: {invalid_perms}")

        # Check for existing role_name
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

        # Invalidate caches for roles and users
        await invalidate_cache_prefix("role")
        await invalidate_cache_prefix("user")
        invalidate_role_cache(db_role.role_id)
        invalidate_user_cache(current_user.user_id)
        logger.info(f"Cache invalidated for role_id: {db_role.role_id} and users")

        # Log action using SystemAction.CREATE_ROLE
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_ROLE,
            table_affected="roles",
            record_id=db_role.role_id,
            old_values=None,
            new_values=db_role.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Role created, role_id: {db_role.role_id}, role_name: {db_role.role_name}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return RoleOut.model_validate(db_role)

    except ValidationError as e:
        logger.error(f"Validation error creating role: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating role: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating role"
        )

async def get_role(
    role_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _= Depends(require_permissions_dependency([Permission.VIEW_ROLE]))
) -> RoleOut:
    """Retrieve a role by ID."""
    try:
        if role_id <= 0:
            raise ValidationError(detail="Invalid role ID")

        cache_key = f"role:{role_id}"
        cached_role = await get_cache(cache_key)
        if cached_role:
            logger.info(f"Cache hit for role_id: {role_id}", extra={"request_id": request_id})
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

        role_object = RoleOut.model_validate(role)
        role_dict = role_object.model_dump(mode='json')  # Use mode='json' for proper serialization
        await set_cache(cache_key, role_dict, ttl=300)
        logger.info(f"Cache set for role_id: {role_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved role, role_id: {role_id}, user_id: {current_user.user_id}",
            extra={"request_id": request_id}
        )
        return role_object

    except ValidationError as e:
        logger.error(f"Validation error retrieving role {role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except RoleNotFoundError as e:
        logger.error(f"Role not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving role {role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving role"
        )

async def list_roles(
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _= Depends(require_permissions_dependency([Permission.VIEW_ROLE]))
) -> List[RoleOut]:
    """Retrieve a list of active roles with pagination."""
    try:
        if skip < 0 or (limit is not None and limit < 0):
            raise ValidationError(detail="Invalid pagination parameters")

        limit = limit or settings.DEFAULT_PAGE_SIZE
        cache_key = f"roles:{skip}:{limit}"
        cached_roles = await get_cache(cache_key)
        if cached_roles:
            logger.info(f"Cache hit for roles list, skip: {skip}, limit: {limit}", extra={"request_id": request_id})
            return [RoleOut(**role) for role in cached_roles]

        query = select(Roles).where(
            Roles.is_active.is_(True),
            Roles.deleted_at.is_(None)
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        roles = result.scalars().all()

        role_objects = [RoleOut.model_validate(role) for role in roles]
        roles_dict = [role.model_dump(mode='json') for role in role_objects]  # Use mode='json' for proper serialization
        await set_cache(cache_key, roles_dict, ttl=300)
        logger.info(f"Cache set for roles list, skip: {skip}, limit: {limit}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(roles)} roles for user_id: {current_user.user_id}",
            extra={"request_id": request_id}
        )
        return role_objects

    except ValidationError as e:
        logger.error(f"Validation error retrieving roles: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving roles: {str(e)}", extra={"request_id": request_id})
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
    request_id: Optional[str] = None,
    _= Depends(require_permissions_dependency([Permission.UPDATE_ROLE]))
) -> RoleOut:
    """Update a role with validation, logging, and cache clearing."""
    try:
        if role_id <= 0:
            raise ValidationError(detail="Invalid role ID")

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
            if not await validate_enum_value(RoleName, update_data["role_name"]):
                raise ValidationError(detail=f"Invalid role name: {update_data['role_name']}")
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
            is_valid, invalid_perms = validate_permissions_list([k for k, v in update_data["permissions"].items() if v])
            if not is_valid:
                raise ValidationError(detail=f"Invalid permissions: {invalid_perms}")

        old_values = db_role.__dict__.copy()
        for key, value in update_data.items():
            setattr(db_role, key, value)
        db_role.updated_at = datetime.now(timezone.utc)
        db.add(db_role)
        await db.commit()
        await db.refresh(db_role)

        # Invalidate caches for roles and users
        await invalidate_cache_prefix("role")
        await invalidate_cache_prefix("user")
        invalidate_role_cache(role_id)
        invalidate_user_cache(current_user.user_id)
        logger.info(f"Cache invalidated for role_id: {role_id} and users")

        # Log action using SystemAction.UPDATE_ROLE
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_ROLE,
            table_affected="roles",
            record_id=role_id,
            old_values=old_values,
            new_values=db_role.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Role updated, role_id: {role_id}, role_name: {db_role.role_name}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return RoleOut.model_validate(db_role)

    except ValidationError as e:
        logger.error(f"Validation error updating role {role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except RoleNotFoundError as e:
        logger.error(f"Role not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error updating role {role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating role"
        )

async def delete_role(
    role_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _= Depends(require_permissions_dependency([Permission.DELETE_ROLE]))
) -> None:
    """Soft delete a role with validation, logging, and cache clearing."""
    try:
        if role_id <= 0:
            raise ValidationError(detail="Invalid role ID")

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
        db.add(db_role)
        await db.commit()

        # Invalidate caches for roles and users
        await invalidate_cache_prefix("role")
        await invalidate_cache_prefix("user")
        invalidate_role_cache(role_id)
        invalidate_user_cache(current_user.user_id)
        logger.info(f"Cache invalidated for role_id: {role_id} and users")

        # Log action using SystemAction.DELETE_ROLE
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_ROLE,
            table_affected="roles",
            record_id=role_id,
            old_values=db_role.__dict__,
            new_values=None,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Role soft deleted, role_id: {role_id}, role_name: {db_role.role_name}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error deleting role {role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except RoleNotFoundError as e:
        logger.error(f"Role not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BusinessLogicError as e:
        logger.error(f"Business logic error deleting role {role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error deleting role {role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting role"
        )