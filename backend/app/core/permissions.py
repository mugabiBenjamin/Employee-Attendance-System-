from typing import List, Optional
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict
from app.core.database import get_db
from app.core.config import settings
from app.core.exceptions import AuthorizationError
from app.core.enums import Permission
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.core.security import get_current_user, oauth2_scheme

class PermissionCheck(BaseModel):
    user_id: int
    required_permissions: List[str]

    model_config = ConfigDict(from_attributes=True)

async def check_permissions(
    required_permissions: List[str],
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> bool:
    """Check if the current user has the required permissions."""
    try:
        # Verify user is active
        if not current_user.is_active:
            raise AuthorizationError(detail="User account is inactive")
        
        # Query user roles with proper joins
        query = (
            select(Roles.permissions)
            .join(UserRoles, UserRoles.role_id == Roles.role_id)
            .where(
                UserRoles.user_id == current_user.user_id,
                UserRoles.is_active == True
            )
        )
        result = await db.execute(query)
        role_permissions = result.scalars().all()
        
        if not role_permissions:
            raise AuthorizationError(detail="No active roles found for user")

        # Combine all permissions from user's roles
        user_permissions = set()
        has_all_permissions = False
        
        for perms in role_permissions:
            if isinstance(perms, dict):
                # Check for all_permissions wildcard first
                if perms.get("all_permissions") is True:
                    has_all_permissions = True
                    break
                
                # Add permissions that are explicitly set to True
                for perm_key, perm_value in perms.items():
                    if perm_value is True:
                        user_permissions.add(perm_key)

        # If user has all_permissions, they can do anything
        if has_all_permissions:
            return True

        # Check if all required permissions are present and enabled
        missing_permissions = []
        for perm in required_permissions:
            if perm not in user_permissions:
                missing_permissions.append(perm)
        
        if missing_permissions:
            raise AuthorizationError(
                detail=f"User lacks required permissions: {', '.join(missing_permissions)}"
            )

        return True

    except AuthorizationError:
        raise
    except Exception as e:
        raise AuthorizationError(detail=f"Permission check failed: {str(e)}")

def require_permissions(required_permissions: List[str]):
    """Decorator to enforce permission checks for FastAPI routes."""
    def decorator(func):
        async def wrapper(*args, current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db), **kwargs):
            await check_permissions(required_permissions, current_user, db)
            return await func(*args, current_user=current_user, db=db, **kwargs)
        return wrapper
    return decorator

# Utility function to get user permissions
async def get_user_permissions(
    user_id: int,
    db: AsyncSession
) -> List[str]:
    """Get all permissions for a specific user."""
    query = (
        select(Roles.permissions)
        .join(UserRoles, UserRoles.role_id == Roles.role_id)
        .where(
            UserRoles.user_id == user_id,
            UserRoles.is_active == True
        )
    )
    result = await db.execute(query)
    role_permissions = result.scalars().all()
    
    user_permissions = set()
    for perms in role_permissions:
        if isinstance(perms, dict):
            if perms.get("all_permissions") is True:
                # Return all defined permissions
                return [perm.value for perm in Permission]
            
            for perm_key, perm_value in perms.items():
                if perm_value is True:
                    user_permissions.add(perm_key)
    
    return list(user_permissions)

# Example usage decorators for common permission checks
def require_employee_permissions():
    return require_permissions([Permission.CLOCK_IN, Permission.CLOCK_OUT])

def require_manager_permissions():
    return require_permissions([Permission.APPROVE_LEAVE, Permission.VIEW_TEAM_ATTENDANCE])

def require_hr_permissions():
    return require_permissions([Permission.MANAGE_EMPLOYEES, Permission.VIEW_ALL_ATTENDANCE])

def require_admin_permissions():
    return require_permissions([Permission.MANAGE_USERS, Permission.MANAGE_ROLES])