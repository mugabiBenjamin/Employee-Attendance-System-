from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.enums import Permission
from app.core.config import Settings, get_settings
from app.services.role_service import (
    create_role as service_create_role,
    get_role as service_get_role,
    list_roles as service_list_roles,
    update_role as service_update_role,
    delete_role as service_delete_role
)
from app.schemas.role import RoleCreate, RoleUpdate, RoleOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/roles", tags=["Roles"])

@router.post("/", 
             response_model=RoleOut, 
             status_code=status.HTTP_201_CREATED,
             summary="Create a new role",
             description="Create a new role.")
@require_permissions([Permission.MANAGE_ROLES])
async def create_role_endpoint(
    role: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> RoleOut:
    """
    Create a new role by delegating to role_service.
    """
    return await service_create_role(role, db, current_user, settings)

@router.get("/{role_id}", 
            response_model=RoleOut,
            summary="Get role by ID",
            description="Retrieve a role by its ID.")
@require_permissions([Permission.MANAGE_ROLES])
async def get_role_endpoint(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> RoleOut:
    """
    Retrieve a role by ID by delegating to role_service.
    """
    return await service_get_role(role_id, db, current_user, settings)

@router.get("/", 
            response_model=List[RoleOut],
            summary="List all roles",
            description="List all active roles with pagination.")
@require_permissions([Permission.MANAGE_ROLES])
async def list_roles_endpoint(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[RoleOut]:
    """
    List all active roles with pagination by delegating to role_service.
    """
    return await service_list_roles(skip, limit, db, current_user, settings)

@router.put("/{role_id}", 
            response_model=RoleOut,
            summary="Update a role",
            description="Update an existing role.")
@require_permissions([Permission.MANAGE_ROLES])
async def update_role_endpoint(
    role_id: int,
    role_update: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> RoleOut:
    """
    Update a role by delegating to role_service.
    """
    return await service_update_role(role_id, role_update, db, current_user, settings)

@router.delete("/{role_id}", 
               status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete a role",
               description="Soft delete a role.")
@require_permissions([Permission.MANAGE_ROLES])
async def delete_role_endpoint(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> None:
    """
    Soft delete a role by delegating to role_service.
    """
    await service_delete_role(role_id, db, current_user, settings)