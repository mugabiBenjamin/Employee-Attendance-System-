from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.enums import Permission
from app.services.department_service import (
    create_department as service_create_department,
    get_department as service_get_department,
    list_departments as service_list_departments,
    update_department as service_update_department,
    delete_department as service_delete_department
)
from app.schemas.department import DepartmentCreate, DepartmentUpdate, DepartmentOut
from app.core.config import Settings, get_settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/departments", tags=["Departments"])

@router.post("/", 
             response_model=DepartmentOut, 
             status_code=status.HTTP_201_CREATED,
             summary="Create a new department",
             description="Create a new department.")
@require_permissions([Permission.MANAGE_DEPARTMENTS])
async def create_department_endpoint(
    department: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> DepartmentOut:
    """
    Create a new department by delegating to department_service.
    """
    return await service_create_department(department, db, current_user, settings)

@router.get("/{department_id}", 
            response_model=DepartmentOut,
            summary="Get department by ID",
            description="Retrieve a department by its ID.")
@require_permissions([Permission.MANAGE_DEPARTMENTS])
async def get_department_endpoint(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> DepartmentOut:
    """
    Retrieve a department by ID by delegating to department_service.
    """
    return await service_get_department(department_id, db, current_user, settings)

@router.get("/", 
            response_model=List[DepartmentOut],
            summary="List all departments",
            description="List all active departments with pagination.")
@require_permissions([Permission.MANAGE_DEPARTMENTS])
async def list_departments_endpoint(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[DepartmentOut]:
    """
    List all active departments with pagination by delegating to department_service.
    """
    return await service_list_departments(skip, limit, db, current_user, settings)

@router.put("/{department_id}", 
            response_model=DepartmentOut,
            summary="Update a department",
            description="Update an existing department.")
@require_permissions([Permission.MANAGE_DEPARTMENTS])
async def update_department_endpoint(
    department_id: int,
    department_update: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> DepartmentOut:
    """
    Update a department by delegating to department_service.
    """
    return await service_update_department(department_id, department_update, db, current_user, settings)

@router.delete("/{department_id}", 
               status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete a department",
               description="Soft delete a department.")
@require_permissions([Permission.MANAGE_DEPARTMENTS])
async def delete_department_endpoint(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> None:
    """
    Soft delete a department by delegating to department_service.
    """
    await service_delete_department(department_id, db, current_user, settings)