from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.user_service import (
    create_user as service_create_user,
    read_user as service_read_user,
    read_users as service_read_users,
    update_user as service_update_user,
    delete_user as service_delete_user,
    get_current_user_profile as service_get_current_user_profile
)
from app.schemas.user import UserCreate, UserUpdate, UserOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])

@router.post("/", 
             response_model=UserOut, 
             status_code=status.HTTP_201_CREATED,
             summary="Create new user",
             description="Create a new user.")
@require_permissions([Permission.MANAGE_USERS])
async def create_new_user_endpoint(
    user: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> UserOut:
    """
    Create a new user by delegating to user_service.
    """
    return await service_create_user(user, current_user, db, settings)

@router.get("/{user_id}", 
            response_model=UserOut,
            summary="Get user by ID",
            description="Retrieve a user by their ID.")
@require_permissions([Permission.MANAGE_USERS])
async def read_user_endpoint(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> UserOut:
    """
    Retrieve a user by ID by delegating to user_service.
    """
    return await service_read_user(user_id, current_user, db, settings)

@router.get("/", 
            response_model=List[UserOut],
            summary="List all users",
            description="List all active users with pagination.")
@require_permissions([Permission.MANAGE_USERS])
async def read_users_endpoint(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[UserOut]:
    """
    List all users by delegating to user_service.
    """
    return await service_read_users(skip, limit, current_user, db, settings)

@router.put("/{user_id}", 
            response_model=UserOut,
            summary="Update user",
            description="Update a user's details.")
@require_permissions([Permission.MANAGE_USERS])
async def update_existing_user_endpoint(
    user_id: int,
    user_update: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> UserOut:
    """
    Update a user by delegating to user_service.
    """
    return await service_update_user(user_id, user_update, current_user, db, settings)

@router.delete("/{user_id}", 
               status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete user",
               description="Soft delete a user.")
@require_permissions([Permission.MANAGE_USERS])
async def delete_existing_user_endpoint(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> None:
    """
    Soft delete a user by delegating to user_service.
    """
    await service_delete_user(user_id, current_user, db, settings)

@router.get("/me/profile", 
            response_model=UserOut,
            summary="Get current user profile",
            description="Retrieve the current authenticated user's profile.")
async def get_current_user_profile_endpoint(
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> UserOut:
    """
    Retrieve the current user's profile by delegating to user_service.
    """
    return await service_get_current_user_profile(current_user, settings)