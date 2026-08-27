from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.utils import get_request_id
from app.services.user_service import (
    create_user as service_create_user,
    read_user as service_read_user,
    read_users as service_read_users,
    update_user as service_update_user,
    delete_user as service_delete_user,
    get_current_user_profile as service_get_current_user_profile
)
from app.schemas.user import UserCreate, UserUpdate, UserOut
from app.core.permissions import require_permissions_dependency
from app.core.enums import Permission

router = APIRouter(prefix="/users", tags=["Users"])

@router.post(
    "/",
    response_model=UserOut,
    status_code=201,
    summary="Create new user"
)
async def create_new_user_endpoint(
    user: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.CREATE_USER]))
) -> UserOut:
    """Create a new user."""
    request_id = get_request_id(request)
    return await service_create_user(user, request, current_user, db, request_id)

@router.get(
    "/{user_id}",
    response_model=UserOut,
    summary="Get user by ID"
)
async def read_user_endpoint(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.VIEW_USER]))
) -> UserOut:
    """Retrieve a user by ID."""
    request_id = get_request_id(request)
    return await service_read_user(user_id, db, request_id)

@router.get(
    "/",
    response_model=List[UserOut],
    summary="List all users"
)
async def read_users_endpoint(
    request: Request,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_USER]))
) -> List[UserOut]:
    """List all active users with pagination."""
    request_id = get_request_id(request)
    return await service_read_users(skip, limit, db, settings, request_id)

@router.put(
    "/{user_id}",
    response_model=UserOut,
    summary="Update user"
)
async def update_existing_user_endpoint(
    user_id: int,
    user_update: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.UPDATE_USER]))
) -> UserOut:
    """Update a user's details."""
    request_id = get_request_id(request)
    return await service_update_user(user_id, user_update, request, current_user, db, request_id)

@router.delete(
    "/{user_id}",
    status_code=204,
    summary="Delete user"
)
async def delete_existing_user_endpoint(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.DELETE_USER]))
) -> None:
    """Soft delete a user."""
    request_id = get_request_id(request)
    await service_delete_user(user_id, request, current_user, db, request_id)

@router.get(
    "/me/profile",
    response_model=UserOut,
    summary="Get current user profile"
)
async def get_current_user_profile_endpoint(
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.VIEW_OWN_PROFILE]))
) -> UserOut:
    """Retrieve the current user's profile."""
    request_id = get_request_id(request)
    return await service_get_current_user_profile(current_user, db, request_id)