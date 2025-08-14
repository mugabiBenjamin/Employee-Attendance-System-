from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict
from app.core.database import get_db
from app.core.enums import Permission
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.core.security import get_current_user
from app.core.exceptions import AuthorizationError
import cachetools
import logging

logger = logging.getLogger(__name__)

# Initialize in-memory caches with TTL of 5 minutes
user_permission_cache = cachetools.TTLCache(maxsize=1000, ttl=300)
role_permission_cache = cachetools.TTLCache(maxsize=100, ttl=300)

class PermissionCheck(BaseModel):
    user_id: int
    required_permissions: List[Permission]

    model_config = ConfigDict(from_attributes=True)

async def get_role_permissions(role_id: int, db: AsyncSession) -> List[str]:
    """Retrieve and cache permissions for a specific role."""
    cache_key = f"role_{role_id}_permissions"
    cached_permissions = role_permission_cache.get(cache_key)
    if cached_permissions is not None:
        return cached_permissions

    try:
        query = select(Roles.permissions).where(
            Roles.role_id == role_id,
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        permissions = result.scalar_one_or_none()

        if not permissions:
            return []

        role_permissions = []
        if isinstance(permissions, dict):
            if permissions.get(Permission.ALL_PERMISSIONS.value, False):
                role_permissions = [perm.value for perm in Permission]
            else:
                role_permissions = [key for key, value in permissions.items() if value is True]

        role_permission_cache[cache_key] = role_permissions
        return role_permissions
    except Exception as e:
        logger.error(f"Error retrieving permissions for role_id {role_id}: {str(e)}")
        return []

async def check_permissions(
    required_permissions: List[Permission],
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> bool:
    """Check if the current user has the required permissions."""
    try:
        # Verify user is active
        if not current_user.is_active:
            raise AuthorizationError(detail="User account is inactive")

        # Convert enum list to string list for processing
        required_perms_str = [perm.value for perm in required_permissions]

        # Check user permission cache
        cache_key = f"user_{current_user.user_id}_permissions"
        cached_permissions = user_permission_cache.get(cache_key)
        if cached_permissions is not None:
            if Permission.ALL_PERMISSIONS.value in cached_permissions:
                return True
            user_permissions = set(cached_permissions)
            missing_permissions = [perm for perm in required_perms_str if perm not in user_permissions]
            if missing_permissions:
                raise AuthorizationError(
                    detail="Missing required permissions",
                    missing_permissions=missing_permissions
                )
            return True

        # Query user roles
        query = select(UserRoles.role_id).where(
            UserRoles.user_id == current_user.user_id,
            UserRoles.is_active == True
        )
        result = await db.execute(query)
        role_ids = result.scalars().all()

        if not role_ids:
            raise AuthorizationError(detail="No active roles assigned to user")

        # Aggregate permissions from all roles
        user_permissions = set()
        for role_id in role_ids:
            role_permissions = await get_role_permissions(role_id, db)
            user_permissions.update(role_permissions)

        # Cache the aggregated permissions
        user_permission_cache[cache_key] = list(user_permissions)

        # Check for ALL_PERMISSIONS wildcard
        if Permission.ALL_PERMISSIONS.value in user_permissions:
            return True

        # Check if all required permissions are present
        missing_permissions = [perm for perm in required_perms_str if perm not in user_permissions]
        if missing_permissions:
            raise AuthorizationError(
                detail="Missing required permissions",
                missing_permissions=missing_permissions
            )

        return True

    except AuthorizationError:
        raise
    except Exception as e:
        logger.error(f"Permission check failed for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Permission check failed"
        )

def require_permissions(required_permissions: List[Permission]):
    """Decorator to enforce permission checks for FastAPI routes."""
    def decorator(func):
        async def wrapper(*args, current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db), **kwargs):
            await check_permissions(required_permissions, current_user, db)
            return await func(*args, current_user=current_user, db=db, **kwargs)
        return wrapper
    return decorator

async def get_user_permissions(
    user_id: int,
    db: AsyncSession
) -> List[str]:
    """Get all permissions for a specific user."""
    try:
        cache_key = f"user_{user_id}_permissions"
        cached_permissions = user_permission_cache.get(cache_key)
        if cached_permissions is not None:
            return cached_permissions

        query = select(UserRoles.role_id).where(
            UserRoles.user_id == user_id,
            UserRoles.is_active == True
        )
        result = await db.execute(query)
        role_ids = result.scalars().all()

        user_permissions = set()
        for role_id in role_ids:
            role_permissions = await get_role_permissions(role_id, db)
            user_permissions.update(role_permissions)

        user_permission_cache[cache_key] = list(user_permissions)
        return list(user_permissions)

    except Exception as e:
        logger.error(f"Failed to retrieve permissions for user_id {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user permissions"
        )

def require_employee_permissions():
    return require_permissions([Permission.CLOCK_IN, Permission.CLOCK_OUT])

def require_manager_permissions():
    return require_permissions([Permission.APPROVE_LEAVE, Permission.VIEW_TEAM_ATTENDANCE])

def require_hr_permissions():
    return require_permissions([Permission.MANAGE_EMPLOYEES, Permission.VIEW_ALL_ATTENDANCE])

def require_admin_permissions():
    return require_permissions([Permission.MANAGE_USERS, Permission.MANAGE_ROLES])