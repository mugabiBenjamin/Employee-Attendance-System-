from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.services.user_department_service import (
    create_user_department as service_create_user_department,
    read_user_department as service_read_user_department,
    read_user_departments as service_read_user_departments,
    update_user_department as service_update_user_department,
    delete_user_department as service_delete_user_department,
    get_user_departments as service_get_user_departments
)
from app.schemas.user_department import UserDepartmentCreate, UserDepartmentUpdate, UserDepartmentOut
from app.core.permissions import require_permissions
from app.core.enums import Permission
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-departments", tags=["User Departments"])

@router.post(
    "/",
    response_model=UserDepartmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user-department assignment",
    description="Create a new user-department assignment with specified details."
)
async def create_user_department_endpoint(
    user_department: UserDepartmentCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.CREATE_USER_DEPARTMENT]))
) -> UserDepartmentOut:
    """Create a new user-department assignment.

    Args:
        user_department: The user-department data to create.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        UserDepartmentOut: The created user-department assignment.

    Raises:
        HTTPException: For validation errors (422), not found (404), conflict (409), authorization errors (403), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_create_user_department(user_department, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error creating user-department assignment: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating user-department assignment: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/{user_department_id}",
    response_model=UserDepartmentOut,
    summary="Get user-department assignment by ID",
    description="Retrieve a specific user-department assignment by its ID."
)
async def read_user_department_endpoint(
    user_department_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.VIEW_USER_DEPARTMENT]))
) -> UserDepartmentOut:
    """Retrieve a user-department assignment by ID.

    Args:
        user_department_id: The ID of the user-department assignment to retrieve.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.

    Returns:
        UserDepartmentOut: The retrieved user-department assignment.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_read_user_department(user_department_id, db, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving user-department assignment {user_department_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving user-department assignment {user_department_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/",
    response_model=List[UserDepartmentOut],
    summary="List user-department assignments",
    description="List user-department assignments with optional filters and pagination."
)
async def read_user_departments_endpoint(
    request: Request,
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_USER_DEPARTMENT]))
) -> List[UserDepartmentOut]:
    """List user-department assignments with optional filters and pagination.

    Args:
        user_id: Optional user ID to filter assignments.
        department_id: Optional department ID to filter assignments.
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: DEFAULT_PAGE_SIZE).
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[UserDepartmentOut]: List of user-department assignments.

    Raises:
        HTTPException: For validation errors (422), not found (404), authorization errors (403), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_read_user_departments(user_id, department_id, skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error listing user-department assignments: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing user-department assignments: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{user_department_id}",
    response_model=UserDepartmentOut,
    summary="Update a user-department assignment",
    description="Update an existing user-department assignment."
)
async def update_user_department_endpoint(
    user_department_id: int,
    user_department_update: UserDepartmentUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.UPDATE_USER_DEPARTMENT]))
) -> UserDepartmentOut:
    """Update a user-department assignment.

    Args:
        user_department_id: The ID of the user-department assignment to update.
        user_department_update: The updated user-department data.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        UserDepartmentOut: The updated user-department assignment.

    Raises:
        HTTPException: For validation errors (422), not found (404), conflict (409), authorization errors (403), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_update_user_department(user_department_id, user_department_update, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error updating user-department assignment {user_department_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating user-department assignment {user_department_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{user_department_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user-department assignment",
    description="Soft delete a user-department assignment."
)
async def delete_user_department_endpoint(
    user_department_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.DELETE_USER_DEPARTMENT]))
) -> None:
    """Soft delete a user-department assignment.

    Args:
        user_department_id: The ID of the user-department assignment to delete.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        None: No content returned on successful deletion.

    Raises:
        HTTPException: For validation errors (422), not found (404), authorization errors (403), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        await service_delete_user_department(user_department_id, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error deleting user-department assignment {user_department_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting user-department assignment {user_department_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/user/{user_id}/departments",
    response_model=List[UserDepartmentOut],
    summary="Get all departments for a user",
    description="Retrieve all active department assignments for a specific user with pagination."
)
async def get_user_departments_endpoint(
    user_id: int,
    request: Request,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_USER_DEPARTMENT]))
) -> List[UserDepartmentOut]:
    """Retrieve all department assignments for a specific user with pagination.

    Args:
        user_id: The ID of the user to retrieve department assignments for.
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: DEFAULT_PAGE_SIZE).
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[UserDepartmentOut]: List of user-department assignments.

    Raises:
        HTTPException: For validation errors (422), not found (404), authorization errors (403), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_get_user_departments(user_id, skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving departments for user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving departments for user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")