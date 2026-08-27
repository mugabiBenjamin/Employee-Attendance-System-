from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.utils import get_request_id
from app.services.user_role_service import (
    create_user_role as service_create_user_role,
    read_user_role as service_read_user_role,
    read_user_roles as service_read_user_roles,
    update_user_role as service_update_user_role,
    delete_user_role as service_delete_user_role,
    get_user_roles as service_get_user_roles,
    get_user_permissions as service_get_user_permissions
)
from app.schemas.user_role import UserRoleCreate, UserRoleUpdate, UserRoleOut
from app.core.permissions import require_permissions_dependency
from app.core.enums import Permission

router = APIRouter(prefix="/user-roles", tags=["User Roles"])

@router.post(
    "/",
    response_model=UserRoleOut,
    status_code=201,
    summary="Create user role assignment"
)
async def create_user_role_endpoint(
    user_role: UserRoleCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.CREATE_USER_ROLE]))
) -> UserRoleOut:
    """Create a user role assignment."""
    request_id = get_request_id(request)
    return await service_create_user_role(user_role, request, current_user, db, request_id)

@router.get(
    "/{user_role_id}",
    response_model=UserRoleOut,
    summary="Get user role assignment by ID"
)
async def read_user_role_endpoint(
    user_role_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.VIEW_USER_ROLE]))
) -> UserRoleOut:
    """Retrieve a user role assignment by ID."""
    request_id = get_request_id(request)
    return await service_read_user_role(user_role_id, db, request_id)

@router.get(
    "/",
    response_model=List[UserRoleOut],
    summary="List user role assignments"
)
async def read_user_roles_endpoint(
    request: Request,
    user_id: Optional[int] = None,
    role_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_USER_ROLE]))
) -> List[UserRoleOut]:
    """List user role assignments with optional filters and pagination."""
    request_id = get_request_id(request)
    return await service_read_user_roles(user_id, role_id, skip, limit, db, settings, request_id)

@router.put(
    "/{user_role_id}",
    response_model=UserRoleOut,
    summary="Update user role assignment"
)
async def update_user_role_endpoint(
    user_role_id: int,
    user_role_update: UserRoleUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.UPDATE_USER_ROLE]))
) -> UserRoleOut:
    """Update a user role assignment."""
    request_id = get_request_id(request)
    return await service_update_user_role(user_role_id, user_role_update, request, current_user, db, request_id)

@router.delete(
    "/{user_role_id}",
    status_code=204,
    summary="Delete user role assignment"
)
async def delete_user_role_endpoint(
    user_role_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.DELETE_USER_ROLE]))
) -> None:
    """Soft delete a user role assignment."""
    request_id = get_request_id(request)
    await service_delete_user_role(user_role_id, request, current_user, db, request_id)

@router.get(
    "/user/{user_id}/roles",
    response_model=List[UserRoleOut],
    summary="Get all roles for a user"
)
async def get_user_roles_endpoint(
    user_id: int,
    request: Request,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_USER_ROLE]))
) -> List[UserRoleOut]:
    """Retrieve all roles for a specific user with pagination."""
    request_id = get_request_id(request)
    return await service_get_user_roles(user_id, skip, limit, db, settings, request_id)

@router.get(
    "/user/{user_id}/permissions",
    response_model=dict,
    summary="Get all permissions for a user"
)
async def get_user_permissions_endpoint(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.VIEW_USER_ROLE]))
) -> dict:
    """Retrieve all permissions for a specific user."""
    request_id = get_request_id(request)
    return await service_get_user_permissions(user_id, db, request_id)