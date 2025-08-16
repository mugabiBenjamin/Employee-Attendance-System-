from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.enums import Permission
from app.core.config import Settings, get_settings
from app.services.employee_hierarchy_service import (
    create_employee_hierarchy as service_create_employee_hierarchy,
    get_employee_hierarchy as service_get_employee_hierarchy,
    list_employee_hierarchies as service_list_employee_hierarchies,
    update_employee_hierarchy as service_update_employee_hierarchy,
    delete_employee_hierarchy as service_delete_employee_hierarchy
)
from app.schemas.employee_hierarchy import (
    EmployeeHierarchyCreate,
    EmployeeHierarchyUpdate,
    EmployeeHierarchyOut
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employee-hierarchy", tags=["Employee Hierarchy"])

@router.post("/", 
             response_model=EmployeeHierarchyOut, 
             status_code=status.HTTP_201_CREATED,
             summary="Create employee hierarchy",
             description="Create an employee hierarchy relationship.")
@require_permissions([Permission.MANAGE_EMPLOYEES])
async def create_employee_hierarchy_endpoint(
    hierarchy: EmployeeHierarchyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> EmployeeHierarchyOut:
    """
    Create an employee hierarchy by delegating to employee_hierarchy_service.
    """
    return await service_create_employee_hierarchy(hierarchy, db, current_user, settings)

@router.get("/{hierarchy_id}", 
            response_model=EmployeeHierarchyOut,
            summary="Get employee hierarchy by ID",
            description="Retrieve an employee hierarchy by ID, restricted to own/team hierarchies or with VIEW_ALL_ATTENDANCE.")
@require_permissions([Permission.VIEW_ALL_ATTENDANCE, Permission.VIEW_TEAM_ATTENDANCE, Permission.VIEW_OWN_ATTENDANCE])
async def get_employee_hierarchy_endpoint(
    hierarchy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> EmployeeHierarchyOut:
    """
    Retrieve an employee hierarchy by ID by delegating to employee_hierarchy_service.
    """
    return await service_get_employee_hierarchy(hierarchy_id, current_user, db, settings)

@router.get("/", 
            response_model=List[EmployeeHierarchyOut],
            summary="List employee hierarchies",
            description="List employee hierarchies, filtered by employee_id or restricted to own/team hierarchies.")
@require_permissions([Permission.VIEW_ALL_ATTENDANCE, Permission.VIEW_TEAM_ATTENDANCE, Permission.VIEW_OWN_ATTENDANCE])
async def list_employee_hierarchies_endpoint(
    employee_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[EmployeeHierarchyOut]:
    """
    List employee hierarchies by delegating to employee_hierarchy_service.
    """
    return await service_list_employee_hierarchies(employee_id, skip, limit, current_user, db, settings)

@router.put("/{hierarchy_id}", 
            response_model=EmployeeHierarchyOut,
            summary="Update employee hierarchy",
            description="Update an employee hierarchy relationship.")
@require_permissions([Permission.MANAGE_EMPLOYEES])
async def update_employee_hierarchy_endpoint(
    hierarchy_id: int,
    hierarchy_update: EmployeeHierarchyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> EmployeeHierarchyOut:
    """
    Update an employee hierarchy by delegating to employee_hierarchy_service.
    """
    return await service_update_employee_hierarchy(hierarchy_id, hierarchy_update, current_user, db, settings)

@router.delete("/{hierarchy_id}", 
               status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete employee hierarchy",
               description="Soft delete an employee hierarchy.")
@require_permissions([Permission.MANAGE_EMPLOYEES])
async def delete_employee_hierarchy_endpoint(
    hierarchy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> None:
    """
    Soft delete an employee hierarchy by delegating to employee_hierarchy_service.
    """
    await service_delete_employee_hierarchy(hierarchy_id, current_user, db, settings)