from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict
from app.core.database import validate_enum_value, get_db
from app.core.enums import Permission, PermissionGroup, PERMISSION_GROUPS
from app.core.security import get_current_user
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.core.exceptions import AuthorizationError
import cachetools
import logging
import anyio

logger = logging.getLogger(__name__)

# Initialize in-memory caches with TTL of 5 minutes
user_permission_cache = cachetools.TTLCache(maxsize=1000, ttl=300)
role_permission_cache = cachetools.TTLCache(maxsize=100, ttl=300)
department_permission_cache = cachetools.TTLCache(maxsize=100, ttl=300)

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
                valid_permissions = [key for key, value in permissions.items() if value is True]
                role_permissions = []
                for perm in valid_permissions:
                    if await validate_enum_value(Permission, perm):
                        role_permissions.append(perm)
                    else:
                        logger.warning(f"Invalid permission '{perm}' for role_id {role_id}")
                
        role_permission_cache[cache_key] = role_permissions
        return role_permissions
    except Exception as e:
        logger.error(f"Error retrieving permissions for role_id {role_id}: {str(e)}")
        return []

async def check_permissions(
    required_permissions: List[Permission],
    current_user: Users,
    db: AsyncSession
) -> bool:
    """Check if the current user has the required permissions."""
    try:
        if not current_user.is_active:
            raise AuthorizationError(detail="User account is inactive")

        required_perms_str = [perm.value for perm in required_permissions]
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

        query = select(UserRoles.role_id).where(
            UserRoles.user_id == current_user.user_id,
            UserRoles.is_active == True
        )
        result = await db.execute(query)
        role_ids = result.scalars().all()

        if not role_ids:
            raise AuthorizationError(detail="No active roles assigned to user")

        user_permissions = set()
        for role_id in role_ids:
            role_permissions = await get_role_permissions(role_id, db)
            user_permissions.update(role_permissions)

        user_permission_cache[cache_key] = list(user_permissions)
        if Permission.ALL_PERMISSIONS.value in user_permissions:
            return True

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

def require_permissions_dependency(required_permissions: List[Permission]):
    """Dependency to enforce permission checks for FastAPI routes."""
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        await check_permissions(required_permissions, current_user, db)
    return inner

def require_any_permissions_dependency(required_permissions: List[Permission]):
    """Dependency that allows access if user has ANY of the required permissions."""
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        user_permissions_raw = await get_user_permissions(current_user.user_id, db)
        user_permissions = set(user_permissions_raw) if user_permissions_raw else set()
        required_perms_str = [perm.value for perm in required_permissions]
        
        if Permission.ALL_PERMISSIONS.value not in user_permissions:
            if not any(perm in user_permissions for perm in required_perms_str):
                raise AuthorizationError(
                    detail=f"Missing any of required permissions: {required_perms_str}"
                )
    return inner

async def get_user_permissions(user_id: int, db: AsyncSession) -> List[str]:
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

async def has_permission(user_id: int, permission: Permission, db: AsyncSession) -> bool:
    """Check if a specific user has a specific permission."""
    try:
        user_permissions = await get_user_permissions(user_id, db)
        return (Permission.ALL_PERMISSIONS.value in user_permissions or 
                permission.value in user_permissions)
    except Exception:
        return False

def get_permissions_for_group(group: PermissionGroup) -> List[Permission]:
    """Get all permissions for a permission group."""
    if not validate_enum_value(PermissionGroup, group.value):
        logger.warning(f"Invalid PermissionGroup value: {group.value}")
        return []
    return PERMISSION_GROUPS.get(group, [])

async def has_role_level_access(user_id: int, required_level: PermissionGroup, db: AsyncSession) -> bool:
    """Check if user has access level equivalent to or higher than required role level."""
    try:
        user_permissions = await get_user_permissions(user_id, db)
        
        if Permission.ALL_PERMISSIONS.value in user_permissions:
            return True
        
        required_permissions = get_permissions_for_group(required_level)
        required_perms_str = [p.value for p in required_permissions]
        
        return all(perm in user_permissions for perm in required_perms_str)
    except Exception:
        return False

def require_employee_access_dependency():
    """Dependency to check if user has employee-level access."""
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        if not await has_role_level_access(current_user.user_id, PermissionGroup.EMPLOYEE, db):
            raise AuthorizationError(detail="Employee access required")
    return inner

def require_manager_access_dependency():
    """Dependency to check if user has manager-level access."""
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        if not await has_role_level_access(current_user.user_id, PermissionGroup.MANAGER, db):
            raise AuthorizationError(detail="Manager access required")
    return inner

def require_hr_access_dependency():
    """Dependency to check if user has HR-level access."""
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        if not await has_role_level_access(current_user.user_id, PermissionGroup.HR, db):
            raise AuthorizationError(detail="HR access required")
    return inner

def require_admin_access_dependency():
    """Dependency to check if user has admin-level access."""
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        if not await has_role_level_access(current_user.user_id, PermissionGroup.ADMIN, db):
            raise AuthorizationError(detail="Admin access required")
    return inner

def require_super_admin_access_dependency():
    """Dependency to check if user has super admin access."""
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        if not await has_role_level_access(current_user.user_id, PermissionGroup.SUPER_ADMIN, db):
            raise AuthorizationError(detail="Super admin access required")
    return inner

# Specific permission dependencies
def require_leave_management_dependency():
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        user_permissions_raw = await get_user_permissions(current_user.user_id, db)
        user_permissions = set(user_permissions_raw) if user_permissions_raw else set()
        
        required_permissions = [
            Permission.VIEW_LEAVE_REQUEST.value,
            Permission.VIEW_TEAM_LEAVE_REQUESTS.value,
            Permission.VIEW_ALL_LEAVE_REQUESTS.value,
            Permission.CREATE_ALL_LEAVE_REQUESTS.value,
            Permission.APPROVE_LEAVE.value,
            Permission.MANAGE_LEAVE.value
        ]
        
        if Permission.ALL_PERMISSIONS.value not in user_permissions:
            if not any(perm in user_permissions for perm in required_permissions):
                raise AuthorizationError(
                    detail=f"Missing any of required permissions: {required_permissions}"
                )
    return inner

def require_attendance_view_dependency():
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        user_permissions_raw = await get_user_permissions(current_user.user_id, db)
        user_permissions = set(user_permissions_raw) if user_permissions_raw else set()
        
        required_permissions = [
            Permission.VIEW_OWN_ATTENDANCE.value,
            Permission.VIEW_TEAM_ATTENDANCE.value,
            Permission.VIEW_ALL_ATTENDANCE.value,
            Permission.VIEW_ATTENDANCE.value
        ]
        
        if Permission.ALL_PERMISSIONS.value not in user_permissions:
            if not any(perm in user_permissions for perm in required_permissions):
                raise AuthorizationError(
                    detail=f"Missing any of required permissions: {required_permissions}"
                )
    return inner

def require_user_management_dependency():
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        user_permissions_raw = await get_user_permissions(current_user.user_id, db)
        user_permissions = set(user_permissions_raw) if user_permissions_raw else set()
        
        required_permissions = [
            Permission.CREATE_USER.value,
            Permission.VIEW_USER.value,
            Permission.UPDATE_USER.value,
            Permission.DELETE_USER.value,
            Permission.MANAGE_USERS.value
        ]
        
        if Permission.ALL_PERMISSIONS.value not in user_permissions:
            if not any(perm in user_permissions for perm in required_permissions):
                raise AuthorizationError(
                    detail=f"Missing any of required permissions: {required_permissions}"
                )
    return inner

def require_workflow_management_dependency():
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        await require_permissions_dependency([Permission.DEFINE_WORKFLOW, Permission.VIEW_WORKFLOWS])(current_user, db)
    return inner

def require_leave_approval_dependency():
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        await require_permissions_dependency([Permission.APPROVE_LEAVE_REQUEST])(current_user, db)
    return inner

def require_overtime_approval_dependency():
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        await require_permissions_dependency([Permission.APPROVE_OVERTIME_RECORD])(current_user, db)
    return inner

def require_department_management_dependency():
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        await require_permissions_dependency([Permission.UPDATE_DEPARTMENT, Permission.CREATE_DEPARTMENT])(current_user, db)
    return inner

def require_overtime_management_dependency():
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        user_permissions_raw = await get_user_permissions(current_user.user_id, db)
        user_permissions = set(user_permissions_raw) if user_permissions_raw else set()
        
        required_permissions = [
            Permission.APPROVE_OVERTIME.value,
            Permission.APPROVE_OVERTIME_RECORD.value,
            Permission.MANAGE_OVERTIME.value
        ]
        
        if Permission.ALL_PERMISSIONS.value not in user_permissions:
            if not any(perm in user_permissions for perm in required_permissions):
                raise AuthorizationError(
                    detail=f"Missing any of required permissions: {required_permissions}"
                )
    return inner

def require_shift_management_dependency():
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        user_permissions_raw = await get_user_permissions(current_user.user_id, db)
        user_permissions = set(user_permissions_raw) if user_permissions_raw else set()
        
        required_permissions = [
            Permission.MANAGE_SHIFT_PATTERNS.value,
            Permission.MANAGE_SHIFT_ASSIGNMENTS.value,
            Permission.CREATE_SHIFT_PATTERN.value,
            Permission.UPDATE_SHIFT_PATTERN.value
        ]
        
        if Permission.ALL_PERMISSIONS.value not in user_permissions:
            if not any(perm in user_permissions for perm in required_permissions):
                raise AuthorizationError(
                    detail=f"Missing any of required permissions: {required_permissions}"
                )
    return inner

def require_emergency_contact_access_dependency():
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        user_permissions_raw = await get_user_permissions(current_user.user_id, db)
        user_permissions = set(user_permissions_raw) if user_permissions_raw else set()
        
        required_permissions = [
            Permission.VIEW_OWN_EMERGENCY_CONTACT.value,
            Permission.VIEW_EMERGENCY_CONTACT.value,
            Permission.UPDATE_EMERGENCY_CONTACT.value
        ]
        
        if Permission.ALL_PERMISSIONS.value not in user_permissions:
            if not any(perm in user_permissions for perm in required_permissions):
                raise AuthorizationError(
                    detail=f"Missing any of required permissions: {required_permissions}"
                )
    return inner

def require_hierarchy_access_dependency():
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        user_permissions_raw = await get_user_permissions(current_user.user_id, db)
        user_permissions = set(user_permissions_raw) if user_permissions_raw else set()
        
        required_permissions = [
            Permission.VIEW_OWN_HIERARCHY.value,
            Permission.VIEW_HIERARCHY.value,
            Permission.UPDATE_HIERARCHY.value
        ]
        
        if Permission.ALL_PERMISSIONS.value not in user_permissions:
            if not any(perm in user_permissions for perm in required_permissions):
                raise AuthorizationError(
                    detail=f"Missing any of required permissions: {required_permissions}"
                )
    return inner

def require_attendance_management_dependency():
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        user_permissions_raw = await get_user_permissions(current_user.user_id, db)
        user_permissions = set(user_permissions_raw) if user_permissions_raw else set()
        
        required_permissions = [
            Permission.MANAGE_ATTENDANCE.value,
            Permission.VIEW_ATTENDANCE.value,
            Permission.VIEW_ALL_ATTENDANCE.value
        ]
        
        if Permission.ALL_PERMISSIONS.value not in user_permissions:
            if not any(perm in user_permissions for perm in required_permissions):
                raise AuthorizationError(
                    detail=f"Missing any of required permissions: {required_permissions}"
                )
    return inner

def require_time_correction_management_dependency():
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        user_permissions_raw = await get_user_permissions(current_user.user_id, db)
        user_permissions = set(user_permissions_raw) if user_permissions_raw else set()
        
        required_permissions = [
            Permission.MANAGE_TIME_CORRECTION.value,
            Permission.CREATE_TIME_CORRECTION.value,
            Permission.UPDATE_TIME_CORRECTION.value,
            Permission.DELETE_TIME_CORRECTION.value
        ]
        
        if Permission.ALL_PERMISSIONS.value not in user_permissions:
            if not any(perm in user_permissions for perm in required_permissions):
                raise AuthorizationError(
                    detail=f"Missing any of required permissions: {required_permissions}"
                )
    return inner

def require_comprehensive_leave_management_dependency():
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        user_permissions_raw = await get_user_permissions(current_user.user_id, db)
        user_permissions = set(user_permissions_raw) if user_permissions_raw else set()
        
        required_permissions = [
            Permission.CREATE_ALL_LEAVE_REQUESTS.value,
            Permission.VIEW_ALL_LEAVE_REQUESTS.value,
            Permission.APPROVE_LEAVE_REQUEST.value,
            Permission.MANAGE_LEAVE.value
        ]
        
        if Permission.ALL_PERMISSIONS.value not in user_permissions:
            if not any(perm in user_permissions for perm in required_permissions):
                raise AuthorizationError(
                    detail=f"Missing any of required permissions: {required_permissions}"
                )
    return inner

def require_system_log_management_dependency():
    async def inner(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
        user_permissions_raw = await get_user_permissions(current_user.user_id, db)
        user_permissions = set(user_permissions_raw) if user_permissions_raw else set()
        
        required_permissions = [
            Permission.VIEW_LOGS.value,
            Permission.DELETE_LOGS.value,
            Permission.CREATE_LOGS.value
        ]
        
        if Permission.ALL_PERMISSIONS.value not in user_permissions:
            if not any(perm in user_permissions for perm in required_permissions):
                raise AuthorizationError(
                    detail=f"Missing any of required permissions: {required_permissions}"
                )
    return inner

async def validate_role_permissions(role_permissions: dict, db: AsyncSession) -> tuple[bool, list[str]]:
    """Validate that all permissions in a role exist in the Permission enum."""
    if not isinstance(role_permissions, dict):
        return False, ["Role permissions must be a dictionary"]
    
    permission_keys = [key for key, value in role_permissions.items() if value is True]
    valid_permissions = []
    invalid_perms = []
    
    for perm in permission_keys:
        if await validate_enum_value(Permission, perm):
            valid_permissions.append(perm)
        else:
            invalid_perms.append(perm)
            logger.warning(f"Invalid permission '{perm}' in role permissions")
    
    return len(invalid_perms) == 0, invalid_perms

async def get_effective_permissions(user_id: int, db: AsyncSession) -> dict:
    """Get user's effective permissions with role hierarchy information."""
    try:
        user_permissions = await get_user_permissions(user_id, db)
        
        role_level = PermissionGroup.EMPLOYEE
        if Permission.ALL_PERMISSIONS.value in user_permissions:
            role_level = PermissionGroup.SUPER_ADMIN
        elif await has_role_level_access(user_id, PermissionGroup.ADMIN, db):
            role_level = PermissionGroup.ADMIN
        elif await has_role_level_access(user_id, PermissionGroup.HR, db):
            role_level = PermissionGroup.HR
        elif await has_role_level_access(user_id, PermissionGroup.MANAGER, db):
            role_level = PermissionGroup.MANAGER
        
        return {
            "user_id": user_id,
            "permissions": user_permissions,
            "effective_role_level": role_level.value,
            "total_permissions": len(user_permissions),
            "has_all_permissions": Permission.ALL_PERMISSIONS.value in user_permissions
        }
    except Exception as e:
        logger.error(f"Error getting effective permissions for user {user_id}: {str(e)}")
        return {
            "user_id": user_id,
            "permissions": [],
            "effective_role_level": "none",
            "total_permissions": 0,
            "has_all_permissions": False,
            "error": str(e)
        }

async def invalidate_user_cache(user_id: int):
    """Invalidate cached permissions for a user."""
    cache_key = f"user_{user_id}_permissions"
    await anyio.to_thread.run_sync(lambda: user_permission_cache.pop(cache_key, None))

def invalidate_role_cache(role_id: int):
    """Invalidate cached permissions for a role."""
    cache_key = f"role_{role_id}_permissions"
    role_permission_cache.pop(cache_key, None)

def invalidate_department_cache(department_id: int):
    """Invalidate cached permissions for a department."""
    cache_key = f"department_{department_id}_permissions"
    department_permission_cache.pop(cache_key, None)

async def invalidate_in_memory_cache_prefix(prefix: str):
    """
    Invalidate all in-memory cached entries (TTLCache) that start with the given prefix.

    This function clears cache entries in user_permission_cache, role_permission_cache,
    and department_permission_cache that match the specified prefix. It is distinct from
    the Redis-based `invalidate_cache_prefix` in `database.py`, which handles Redis cache keys.

    Args:
        prefix (str): The prefix to match cache keys against.
    """
    try:
        keys_to_remove = []
        
        for key in list(user_permission_cache.keys()):
            if str(key).startswith(prefix):
                keys_to_remove.append(('user', key))
        
        for key in list(role_permission_cache.keys()):
            if str(key).startswith(prefix):
                keys_to_remove.append(('role', key))
                
        for key in list(department_permission_cache.keys()):
            if str(key).startswith(prefix):
                keys_to_remove.append(('dept', key))
        
        for cache_type, key in keys_to_remove:
            if cache_type == 'user':
                await anyio.to_thread.run_sync(lambda: user_permission_cache.pop(key, None))
            elif cache_type == 'role':
                await anyio.to_thread.run_sync(lambda: role_permission_cache.pop(key, None))
            elif cache_type == 'dept':
                await anyio.to_thread.run_sync(lambda: department_permission_cache.pop(key, None))
                
        logger.debug(f"Invalidated {len(keys_to_remove)} cache entries with prefix: {prefix}")
        
    except Exception as e:
        logger.error(f"Error invalidating cache with prefix {prefix}: {str(e)}")