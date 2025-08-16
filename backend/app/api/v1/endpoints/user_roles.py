from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.user_role_service import (
    create_user_role as service_create_user_role,
    read_user_role as service_read_user_role,
    read_user_roles as service_read_user_roles,
    update_user_role as service_update_user_role,
    delete_user_role as service_delete_user_role,
    get_user_roles as service_get_user_roles
)
from app.schemas.user_role import UserRoleCreate, UserRoleUpdate, UserRoleOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-roles", tags=["User Roles"])

@router.post("/", 
             response_model=UserRoleOut, 
             status_code=status.HTTP_201_CREATED,
             summary="Create user role assignment",
             description="Create a new user role assignment.")
@require_permissions([Permission.MANAGE_ROLES])
async def create_user_role_endpoint(
    user_role: UserRoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> UserRoleOut:
    """
    Create a user role assignment by delegating to user_role_service.
    """
    return await service_create_user_role(user_role, current_user, db, settings)

@router.get("/{user_role_id}", 
            response_model=UserRoleOut,
            summary="Get user role assignment by ID",
            description="Retrieve a user role assignment by its ID.")
@require_permissions([Permission.MANAGE_ROLES])
async def read_user_role_endpoint(
    user_role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> UserRoleOut:
    """
    Retrieve a user role assignment by ID by delegating to user_role_service.
    """
    return await service_read_user_role(user_role_id, current_user, db, settings)

@router.get("/", 
            response_model=List[UserRoleOut],
            summary="List user role assignments",
            description="List user role assignments with optional filters.")
@require_permissions([Permission.MANAGE_ROLES])
async def read_user_roles_endpoint(
    user_id: Optional[int] = None,
    role_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[UserRoleOut]:
    """
    List user role assignments by delegating to user_role_service.
    """
    return await service_read_user_roles(user_id, role_id, skip, limit, current_user, db, settings)

@router.put("/{user_role_id}", 
            response_model=UserRoleOut,
            summary="Update user role assignment",
            description="Update an existing user role assignment.")
@require_permissions([Permission.MANAGE_ROLES])
async def update_user_role_endpoint(
    user_role_id: int,
    user_role_update: UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> UserRoleOut:
    """
    Update a user role assignment by delegating to user_role_service.
    """
    return await service_update_user_role(user_role_id, user_role_update, current_user, db, settings)

@router.delete("/{user_role_id}", 
               status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete user role assignment",
               description="Soft delete a user role assignment.")
@require_permissions([Permission.MANAGE_ROLES])
async def delete_user_role_endpoint(
    user_role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> None:
    """
    Soft delete a user role assignment by delegating to user_role_service.
    """
    await service_delete_user_role(user_role_id, current_user, db, settings)

@router.get("/user/{user_id}/roles", 
            response_model=List[UserRoleOut],
            summary="Get all roles for a user",
            description="Retrieve all active roles for a specific user.")
@require_permissions([Permission.MANAGE_ROLES])
async def get_user_roles_endpoint(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[UserRoleOut]:
    """
    Retrieve all roles for a specific user by delegating to user_role_service.
    """
    return await service_get_user_roles(user_id, current_user, db, settings)