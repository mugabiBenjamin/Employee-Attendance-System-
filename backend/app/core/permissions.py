from typing import List, Optional
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict
from app.core.database import get_db
from app.core.config import settings
from app.core.exceptions import AuthorizationError
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.models.roles import Roles

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
        # Query user roles
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

        # Combine all permissions from user's roles
        user_permissions = set()
        for perms in role_permissions:
            if isinstance(perms, dict):
                user_permissions.update(perms.keys())

        # Check if all required permissions are present
        if not all(perm in user_permissions for perm in required_permissions):
            # Check for 'all_permissions' wildcard
            if "all_permissions" not in user_permissions:
                raise AuthorizationError(
                    detail=f"User lacks required permissions: {', '.join(required_permissions)}"
                )

        return True

    except Exception as e:
        raise AuthorizationError(detail=f"Permission check failed: {str(e)}")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Users:
    """Retrieve the current user from JWT token (imported from security.py for dependency)."""
    from app.core.security import get_current_user
    return await get_current_user(token, db)

def require_permissions(required_permissions: List[str]):
    """Decorator to enforce permission checks for FastAPI routes."""
    def decorator(func):
        async def wrapper(*args, current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db), **kwargs):
            await check_permissions(required_permissions, current_user, db)
            return await func(*args, current_user=current_user, db=db, **kwargs)
        return wrapper
    return decorator

# Example usage in routes (not executed, for reference):
# @router.get("/protected", dependencies=[Depends(require_permissions(["view_reports"]))])
# async def protected_route():
#     return {"message": "Access granted"}