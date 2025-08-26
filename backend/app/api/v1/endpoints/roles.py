from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.services.role_service import (
    create_role,
    get_role,
    list_roles,
    update_role,
    delete_role
)
from app.schemas.role import RoleCreate, RoleUpdate, RoleOut
from app.core.permissions import require_permissions
from app.core.enums import Permission
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/roles", tags=["Roles"])

@router.post(
    "/",
    response_model=RoleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new role",
    description="Create a new role with specified permissions."
)
async def create_role_endpoint(
    role: RoleCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.CREATE_ROLE]))
) -> RoleOut:
    """Create a new role.

    Args:
        role: Role creation data.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        RoleOut: The created role.

    Raises:
        HTTPException: For validation errors (422), conflict (409), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await create_role(role, request, current_user, db, request_id)
    except HTTPException as e:
        logger.error(f"Error creating role: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating role: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/{role_id}",
    response_model=RoleOut,
    summary="Get role by ID",
    description="Retrieve a specific role by its ID."
)
async def get_role_endpoint(
    role_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    # _: bool = Depends(require_permissions([Permission.VIEW_ROLE]))
) -> RoleOut:
    """Retrieve a role by ID.

    Args:
        role_id: The ID of the role to retrieve.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        RoleOut: The retrieved role.

    Raises:
        HTTPException: For not found (404) or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await get_role(role_id, current_user, db, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving role {role_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving role {role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/",
    response_model=List[RoleOut],
    summary="List all roles",
    description="List all active roles with pagination."
)
async def list_roles_endpoint(
    request: Request,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    # _: bool = Depends(require_permissions([Permission.VIEW_ROLE]))
) -> List[RoleOut]:
    """List all active roles with pagination.

    Args:
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return (default: DEFAULT_PAGE_SIZE).
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[RoleOut]: List of active roles.

    Raises:
        HTTPException: For validation errors (422) or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await list_roles(skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error listing roles: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing roles: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{role_id}",
    response_model=RoleOut,
    summary="Update a role",
    description="Update an existing role with specified permissions."
)
async def update_role_endpoint(
    role_id: int,
    role_update: RoleUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.UPDATE_ROLE]))
) -> RoleOut:
    """Update a role.

    Args:
        role_id: The ID of the role to update.
        role_update: Role update data.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        RoleOut: The updated role.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await update_role(role_id, role_update, request, current_user, db, request_id)
    except HTTPException as e:
        logger.error(f"Error updating role {role_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating role {role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a role",
    description="Soft delete a role."
)
async def delete_role_endpoint(
    role_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.DELETE_ROLE]))
) -> None:
    """Soft delete a role.

    Args:
        role_id: The ID of the role to delete.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        None: No content returned on successful deletion.

    Raises:
        HTTPException: For validation errors (422), not found (404), business logic errors (422), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        await delete_role(role_id, request, current_user, db, request_id)
    except HTTPException as e:
        logger.error(f"Error deleting role {role_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting role {role_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")