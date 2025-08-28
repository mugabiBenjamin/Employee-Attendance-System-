from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
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
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])

@router.post(
    "/",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create new user",
    description="Create a new user."
)
async def create_new_user_endpoint(
    user: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.CREATE_USER]))
) -> UserOut:
    """Create a new user.

    Args:
        user: The user data to create.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        current_user: The authenticated user performing the action.
        settings: Application settings.

    Returns:
        UserOut: The created user.

    Raises:
        HTTPException: For validation errors (422), conflict (409), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_create_user(user, request, current_user, db, request_id)
    except HTTPException as e:
        logger.error(f"Error creating user: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating user: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/{user_id}",
    response_model=UserOut,
    summary="Get user by ID",
    description="Retrieve a user by their ID."
)
async def read_user_endpoint(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.VIEW_USER]))
) -> UserOut:
    """Retrieve a user by ID.

    Args:
        user_id: The ID of the user to retrieve.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.

    Returns:
        UserOut: The retrieved user.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_read_user(user_id, db, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/",
    response_model=List[UserOut],
    summary="List all users",
    description="List all active users with pagination."
)
async def read_users_endpoint(
    request: Request,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_USER]))
) -> List[UserOut]:
    """List all active users with pagination.

    Args:
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: DEFAULT_PAGE_SIZE).
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[UserOut]: List of active users.

    Raises:
        HTTPException: For validation errors (422) or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_read_users(skip, limit, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error listing users: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing users: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{user_id}",
    response_model=UserOut,
    summary="Update user",
    description="Update a user's details."
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
    """Update a user's details.

    Args:
        user_id: The ID of the user to update.
        user_update: The updated user data.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        current_user: The authenticated user performing the action.
        settings: Application settings.

    Returns:
        UserOut: The updated user.

    Raises:
        HTTPException: For validation errors (422), not found (404), conflict (409), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_update_user(user_id, user_update, request, current_user, db, request_id)
    except HTTPException as e:
        logger.error(f"Error updating user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Soft delete a user."
)
async def delete_existing_user_endpoint(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.DELETE_USER]))
) -> None:
    """Soft delete a user.

    Args:
        user_id: The ID of the user to delete.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        current_user: The authenticated user performing the action.
        settings: Application settings.

    Returns:
        None: No content returned on successful deletion.

    Raises:
        HTTPException: For validation errors (422), not found (404), business logic errors (422), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        await service_delete_user(user_id, request, current_user, db, request_id)
    except HTTPException as e:
        logger.error(f"Error deleting user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/me/profile",
    response_model=UserOut,
    summary="Get current user profile",
    description="Retrieve the current authenticated user's profile."
)
async def get_current_user_profile_endpoint(
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.VIEW_OWN_PROFILE]))
) -> UserOut:
    """Retrieve the current user's profile.

    Args:
        current_user: The authenticated user.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.

    Returns:
        UserOut: The current user's profile.

    Raises:
        HTTPException: For not found (404) or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_get_current_user_profile(current_user, db, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving profile for user {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving profile for user {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")