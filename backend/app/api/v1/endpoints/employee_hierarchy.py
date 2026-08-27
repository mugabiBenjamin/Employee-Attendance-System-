from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.utils import get_request_id
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
from app.core.permissions import require_permissions_dependency
from app.core.enums import Permission

router = APIRouter(prefix="/employee-hierarchy", tags=["Employee Hierarchy"])

@router.post(
    "/",
    response_model=EmployeeHierarchyOut,
    status_code=201,
    summary="Create employee hierarchy"
)
async def create_employee_hierarchy_endpoint(
    hierarchy: EmployeeHierarchyCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.CREATE_HIERARCHY]))
) -> EmployeeHierarchyOut:
    """Create a new employee-supervisor relationship."""
    request_id = get_request_id(request)
    return await create_employee_hierarchy(hierarchy, request, current_user, db, settings, request_id)

@router.get(
    "/{hierarchy_id}",
    response_model=EmployeeHierarchyOut,
    summary="Get employee hierarchy by ID"
)
async def get_employee_hierarchy_endpoint(
    hierarchy_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.VIEW_HIERARCHY, Permission.VIEW_OWN_HIERARCHY]))
) -> EmployeeHierarchyOut:
    """Retrieve an employee hierarchy by ID."""
    request_id = get_request_id(request)
    return await get_employee_hierarchy(hierarchy_id, current_user, db, request_id)

@router.get(
    "/",
    response_model=List[EmployeeHierarchyOut],
    summary="List employee hierarchies"
)
async def list_employee_hierarchies_endpoint(
    request: Request,
    employee_id: Optional[int] = None,
    department_id: Optional[int] = None,
    supervisor_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_HIERARCHY, Permission.VIEW_OWN_HIERARCHY]))
) -> List[EmployeeHierarchyOut]:
    """List employee hierarchies with optional filters and pagination."""
    request_id = get_request_id(request)
    return await list_employee_hierarchies(employee_id, department_id, supervisor_id, skip, limit, current_user, db, settings, request_id)

@router.put(
    "/{hierarchy_id}",
    response_model=EmployeeHierarchyOut,
    summary="Update employee hierarchy"
)
async def update_employee_hierarchy_endpoint(
    hierarchy_id: int,
    hierarchy_update: EmployeeHierarchyUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.UPDATE_HIERARCHY]))
) -> EmployeeHierarchyOut:
    """Update an employee hierarchy."""
    request_id = get_request_id(request)
    return await update_employee_hierarchy(hierarchy_id, hierarchy_update, request, current_user, db, settings, request_id)

@router.delete(
    "/{hierarchy_id}",
    status_code=204,
    summary="Delete employee hierarchy"
)
async def delete_employee_hierarchy_endpoint(
    hierarchy_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.DELETE_HIERARCHY]))
) -> None:
    """Soft delete an employee hierarchy."""
    request_id = get_request_id(request)
    await delete_employee_hierarchy(hierarchy_id, request, current_user, db, settings, request_id)