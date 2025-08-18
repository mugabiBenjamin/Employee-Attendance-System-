from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.department_service import (
    create_department,
    get_department,
    list_departments,
    update_department,
    delete_department
)
from app.schemas.department import DepartmentCreate, DepartmentUpdate, DepartmentOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/departments", tags=["Departments"])

@router.post(
    "/",
    response_model=DepartmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new department",
    description="Create a new department with provided details."
)
@require_permissions([Permission.CREATE_DEPARTMENT])
async def create_department_endpoint(
    department: DepartmentCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> DepartmentOut:
    """Create a new department.

    Args:
        department: Department creation data.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        DepartmentOut: The created department.
    """
    return await create_department(department, request, current_user, db)

@router.get(
    "/{department_id}",
    response_model=DepartmentOut,
    summary="Get department by ID",
    description="Retrieve a department by its ID."
)
@require_permissions([Permission.VIEW_DEPARTMENT])
async def get_department_endpoint(
    department_id: int,
    db: AsyncSession = Depends(get_db)
) -> DepartmentOut:
    """Retrieve a department by ID.

    Args:
        department_id: The ID of the department to retrieve.
        db: Database session dependency.

    Returns:
        DepartmentOut: The retrieved department.
    """
    return await get_department(department_id, db)

@router.get(
    "/",
    response_model=List[DepartmentOut],
    summary="List all departments",
    description="Retrieve a list of active departments with pagination."
)
@require_permissions([Permission.VIEW_DEPARTMENT])
async def list_departments_endpoint(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[DepartmentOut]:
    """List all active departments with pagination.

    Args:
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[DepartmentOut]: List of active departments.
    """
    return await list_departments(skip, limit, db, settings)

@router.put(
    "/{department_id}",
    response_model=DepartmentOut,
    summary="Update a department",
    description="Update an existing department with provided details."
)
@require_permissions([Permission.UPDATE_DEPARTMENT])
async def update_department_endpoint(
    department_id: int,
    department_update: DepartmentUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> DepartmentOut:
    """Update a department.

    Args:
        department_id: The ID of the department to update.
        department_update: Department update data.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        DepartmentOut: The updated department.
    """
    return await update_department(department_id, department_update, request, current_user, db)

@router.delete(
    "/{department_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a department",
    description="Soft delete a department by its ID."
)
@require_permissions([Permission.DELETE_DEPARTMENT])
async def delete_department_endpoint(
    department_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> None:
    """Soft delete a department.

    Args:
        department_id: The ID of the department to delete.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.
    """
    await delete_department(department_id, request, current_user, db)