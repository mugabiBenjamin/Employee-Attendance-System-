from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.user_role_service import (
    create_user_role as service_create_user_role,
    read_user_role as service_read_user_role,
    read_user_roles as service_read_user_roles,
    update_user_role as service_update_user_role,
    delete_user_role as service_delete_user_role
)
from app.schemas.user_role import UserRoleCreate, UserRoleUpdate, UserRoleOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-roles", tags=["User Roles"])

@router.post(
    "/",
    response_model=UserRoleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create user role assignment",
    description="Create a new user role assignment."
)
@require_permissions([Permission.CREATE_USER_ROLE])
async def create_user_role_endpoint(
    user_role: UserRoleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> UserRoleOut:
    """
    Create a user role assignment.

    Args:
        user_role: The user-role assignment data to create.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        current_user: The authenticated user performing the action.
        settings: Application settings.

    Returns:
        UserRoleOut: The created user-role assignment.

    Raises:
        HTTPException: For validation errors (422), not found (404), conflict (409), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_create_user_role(user_role, request, current_user, db, request_id)
    except HTTPException as e:
        logger.error(f"Error creating user role assignment: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating user role assignment: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/{user_role_id}",
    response_model=UserRoleOut,
    summary="Get user role assignment by ID",
    description="Retrieve a user role assignment by its ID."
)
@require_permissions([Permission.VIEW_USER_ROLE])
async def read_user_role_endpoint(
    user_role_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> UserRoleOut:
    """
    Retrieve a user role assignment by ID.

    Args:
        user_role_id: The ID of the user-role assignment to retrieve.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.

    Returns:
        UserRoleOut: The retrieved user-role assignment.

    Raises:
        HTTPException: For not found (404) or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_read_user_role(user_role_id, db, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving user role assignment {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving user role assignment {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/",
    response_model=List[UserRoleOut],
    summary="List user role assignments",
    description="List user role assignments with optional filters."
)
@require_permissions([Permission.VIEW_USER_ROLE])
async def read_user_roles_endpoint(
    request: Request,
    user_id: Optional[int] = None,
    role_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[UserRoleOut]:
    """
    List user role assignments with optional filters.

    Args:
        user_id: Optional ID of the user to filter assignments (default: None).
        role_id: Optional ID of the role to filter assignments (default: None).
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: 50).
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[UserRoleOut]: List of user-role assignments.

    Raises:
        HTTPException: For not found (404) or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_read_user_roles(user_id, role_id, skip, limit, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error listing user role assignments: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing user role assignments: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{user_role_id}",
    response_model=UserRoleOut,
    summary="Update user role assignment",
    description="Update an existing user role assignment."
)
@require_permissions([Permission.UPDATE_USER_ROLE])
async def update_user_role_endpoint(
    user_role_id: int,
    user_role_update: UserRoleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> UserRoleOut:
    """
    Update a user role assignment.

    Args:
        user_role_id: The ID of the user-role assignment to update.
        user_role_update: The updated user-role assignment data.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        current_user: The authenticated user performing the action.
        settings: Application settings.

    Returns:
        UserRoleOut: The updated user-role assignment.

    Raises:
        HTTPException: For validation errors (422), not found (404), conflict (409), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_update_user_role(user_role_id, user_role_update, request, current_user, db, request_id)
    except HTTPException as e:
        logger.error(f"Error updating user role assignment {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating user role assignment {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{user_role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user role assignment",
    description="Soft delete a user role assignment."
)
@require_permissions([Permission.DELETE_USER_ROLE])
async def delete_user_role_endpoint(
    user_role_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> None:
    """
    Soft delete a user role assignment.

    Args:
        user_role_id: The ID of the user-role assignment to delete.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        current_user: The authenticated user performing the action.
        settings: Application settings.

    Returns:
        None: No content returned on successful deletion.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        await service_delete_user_role(user_role_id, request, current_user, db, request_id)
    except HTTPException as e:
        logger.error(f"Error deleting user role assignment {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting user role assignment {user_role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/user/{user_id}/roles",
    response_model=List[UserRoleOut],
    summary="Get all roles for a user",
    description="Retrieve all active roles for a specific user."
)
@require_permissions([Permission.VIEW_USER_ROLE])
async def get_user_roles_endpoint(
    request: Request,
    user_id: int,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[UserRoleOut]:
    """
    Retrieve all roles for a specific user.

    Args:
        user_id: The ID of the user to retrieve role assignments for.
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: 50).
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[UserRoleOut]: List of user-role assignments for the specified user.

    Raises:
        HTTPException: For not found (404) or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_read_user_roles(user_id=user_id, role_id=None, skip=skip, limit=limit, db=db, settings=settings, request_id=request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving roles for user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving roles for user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")