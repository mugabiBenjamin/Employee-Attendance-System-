from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.user_department_service import (
    create_user_department as service_create_user_department,
    read_user_department as service_read_user_department,
    read_user_departments as service_read_user_departments,
    update_user_department as service_update_user_department,
    delete_user_department as service_delete_user_department,
    get_user_departments as service_get_user_departments
)
from app.schemas.user_department import UserDepartmentCreate, UserDepartmentUpdate, UserDepartmentOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-departments", tags=["User Departments"])

@router.post("/", 
             response_model=UserDepartmentOut, 
             status_code=status.HTTP_201_CREATED,
             summary="Create user department assignment",
             description="Create a new user department assignment.")
@require_permissions([Permission.MANAGE_DEPARTMENTS])
async def create_user_department_endpoint(
    user_department: UserDepartmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> UserDepartmentOut:
    """
    Create a user department assignment by delegating to user_department_service.
    """
    return await service_create_user_department(user_department, current_user, db, settings)

@router.get("/{user_department_id}", 
            response_model=UserDepartmentOut,
            summary="Get user department assignment by ID",
            description="Retrieve a user department assignment by its ID.")
@require_permissions([Permission.VIEW_ALL_ATTENDANCE, Permission.MANAGE_DEPARTMENTS])
async def read_user_department_endpoint(
    user_department_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> UserDepartmentOut:
    """
    Retrieve a user department assignment by ID by delegating to user_department_service.
    """
    return await service_read_user_department(user_department_id, current_user, db, settings)

@router.get("/", 
            response_model=List[UserDepartmentOut],
            summary="List user department assignments",
            description="List user department assignments with optional filters.")
@require_permissions([Permission.VIEW_ALL_ATTENDANCE, Permission.MANAGE_DEPARTMENTS])
async def read_user_departments_endpoint(
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[UserDepartmentOut]:
    """
    List user department assignments by delegating to user_department_service.
    """
    return await service_read_user_departments(user_id, department_id, skip, limit, current_user, db, settings)

@router.put("/{user_department_id}", 
            response_model=UserDepartmentOut,
            summary="Update user department assignment",
            description="Update an existing user department assignment.")
@require_permissions([Permission.MANAGE_DEPARTMENTS])
async def update_user_department_endpoint(
    user_department_id: int,
    user_department_update: UserDepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> UserDepartmentOut:
    """
    Update a user department assignment by delegating to user_department_service.
    """
    return await service_update_user_department(user_department_id, user_department_update, current_user, db, settings)

@router.delete("/{user_department_id}", 
               status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete user department assignment",
               description="Soft delete a user department assignment.")
@require_permissions([Permission.MANAGE_DEPARTMENTS])
async def delete_user_department_endpoint(
    user_department_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> None:
    """
    Soft delete a user department assignment by delegating to user_department_service.
    """
    await service_delete_user_department(user_department_id, current_user, db, settings)

@router.get("/user/{user_id}/departments", 
            response_model=List[UserDepartmentOut],
            summary="Get all departments for a user",
            description="Retrieve all active departments for a specific user.")
@require_permissions([Permission.VIEW_ALL_ATTENDANCE, Permission.MANAGE_DEPARTMENTS])
async def get_user_departments_endpoint(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[UserDepartmentOut]:
    """
    Retrieve all departments for a specific user by delegating to user_department_service.
    """
    return await service_get_user_departments(user_id, current_user, db, settings)