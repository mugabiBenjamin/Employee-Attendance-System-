from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.employee_hierarchy_service import (
    create_employee_hierarchy,
    get_employee_hierarchy,
    list_employee_hierarchies,
    update_employee_hierarchy,
    delete_employee_hierarchy
)
from app.schemas.employee_hierarchy import (
    EmployeeHierarchyCreate,
    EmployeeHierarchyUpdate,
    EmployeeHierarchyOut
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employee-hierarchy", tags=["Employee Hierarchy"])

@router.post(
    "/",
    response_model=EmployeeHierarchyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create employee hierarchy",
    description="Create a new employee-manager relationship."
)
@require_permissions([Permission.CREATE_HIERARCHY])
async def create_employee_hierarchy_endpoint(
    hierarchy: EmployeeHierarchyCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> EmployeeHierarchyOut:
    """Create an employee hierarchy.

    Args:
        hierarchy: Hierarchy creation data.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        EmployeeHierarchyOut: The created hierarchy.
    """
    return await create_employee_hierarchy(hierarchy, request, current_user, db)

@router.get(
    "/{hierarchy_id}",
    response_model=EmployeeHierarchyOut,
    summary="Get employee hierarchy by ID",
    description="Retrieve an employee hierarchy by ID."
)
@require_permissions([Permission.VIEW_HIERARCHY, Permission.VIEW_OWN_HIERARCHY])
async def get_employee_hierarchy_endpoint(
    hierarchy_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> EmployeeHierarchyOut:
    """Retrieve an employee hierarchy by ID.

    Args:
        hierarchy_id: The ID of the hierarchy to retrieve.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        EmployeeHierarchyOut: The retrieved hierarchy.
    """
    return await get_employee_hierarchy(hierarchy_id, current_user, db)

@router.get(
    "/",
    response_model=List[EmployeeHierarchyOut],
    summary="List employee hierarchies",
    description="Retrieve a list of employee hierarchies, optionally filtered by employee_id."
)
@require_permissions([Permission.VIEW_HIERARCHY, Permission.VIEW_OWN_HIERARCHY])
async def list_employee_hierarchies_endpoint(
    employee_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[EmployeeHierarchyOut]:
    """List employee hierarchies with pagination.

    Args:
        employee_id: Optional employee ID to filter hierarchies.
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return.
        current_user: The authenticated user.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[EmployeeHierarchyOut]: List of employee hierarchies.
    """
    return await list_employee_hierarchies(employee_id, skip, limit, current_user, db, settings)

@router.put(
    "/{hierarchy_id}",
    response_model=EmployeeHierarchyOut,
    summary="Update employee hierarchy",
    description="Update an existing employee hierarchy."
)
@require_permissions([Permission.UPDATE_HIERARCHY])
async def update_employee_hierarchy_endpoint(
    hierarchy_id: int,
    hierarchy_update: EmployeeHierarchyUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> EmployeeHierarchyOut:
    """Update an employee hierarchy.

    Args:
        hierarchy_id: The ID of the hierarchy to update.
        hierarchy_update: Hierarchy update data.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        EmployeeHierarchyOut: The updated hierarchy.
    """
    return await update_employee_hierarchy(hierarchy_id, hierarchy_update, request, current_user, db)

@router.delete(
    "/{hierarchy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete employee hierarchy",
    description="Soft delete an employee hierarchy."
)
@require_permissions([Permission.DELETE_HIERARCHY])
async def delete_employee_hierarchy_endpoint(
    hierarchy_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> None:
    """Soft delete an employee hierarchy.

    Args:
        hierarchy_id: The ID of the hierarchy to delete.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.
    """
    await delete_employee_hierarchy(hierarchy_id, request, current_user, db)