from fastapi import APIRouter, Depends, Request
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
from app.core.permissions import require_permissions_dependency
from app.core.enums import Permission
from app.core.utils import get_request_id

router = APIRouter(prefix="/roles", tags=["Roles"])

@router.post(
    "/",
    response_model=RoleOut,
    status_code=201,
    summary="Create a new role"
)
async def create_role_endpoint(
    role: RoleCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.CREATE_ROLE]))
) -> RoleOut:
    """Create a new role."""
    request_id = get_request_id(request)
    return await create_role(role, request, current_user, db, request_id)

@router.get(
    "/{role_id}",
    response_model=RoleOut,
    summary="Get role by ID"
)
async def get_role_endpoint(
    role_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.VIEW_ROLE]))
) -> RoleOut:
    """Retrieve a role by ID."""
    request_id = get_request_id(request)
    return await get_role(role_id, current_user, db, request_id)

@router.get(
    "/",
    response_model=List[RoleOut],
    summary="List all roles"
)
async def list_roles_endpoint(
    request: Request,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_ROLE]))
) -> List[RoleOut]:
    """List all active roles with pagination."""
    request_id = get_request_id(request)
    return await list_roles(skip, limit, current_user, db, settings, request_id)

@router.put(
    "/{role_id}",
    response_model=RoleOut,
    summary="Update a role"
)
async def update_role_endpoint(
    role_id: int,
    role_update: RoleUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.UPDATE_ROLE]))
) -> RoleOut:
    """Update a role."""
    request_id = get_request_id(request)
    return await update_role(role_id, role_update, request, current_user, db, request_id)

@router.delete(
    "/{role_id}",
    status_code=204,
    summary="Delete a role"
)
async def delete_role_endpoint(
    role_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.DELETE_ROLE]))
) -> None:
    """Soft delete a role."""
    request_id = get_request_id(request)
    await delete_role(role_id, request, current_user, db, request_id)