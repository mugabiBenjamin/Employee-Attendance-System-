from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.user import DepartmentCreate, DepartmentUpdate, DepartmentOut
from app.services.department_service import (
    create_department, 
    get_department_by_id, 
    get_departments, 
    update_department, 
    delete_department
)
from app.api.deps import get_db_session, get_current_active_user
from app.services.auth_service import check_user_permission
from app.models.user import User
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

async def is_admin_or_manager(db: AsyncSession, user: User) -> bool:
    from sqlmodel import select
    from app.models.user_roles import UserRoles 
    from app.models.user_roles import Role
    query = select(UserRoles).join(Role).where(
        UserRoles.user_id == user.user_id,
        UserRoles.is_active == True,
        Role.role_name.in_(["Manager", "HR", "Admin", "Super_Admin"])
    )
    result = await db.execute(query)
    return result.first() is not None

@router.post("/", 
    response_model=DepartmentOut, 
    status_code=status.HTTP_201_CREATED,
    summary="Create new department",
    description="Create a new department. Requires manage_departments permission."
)
async def create_new_department(
    department: DepartmentCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new department in the system."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_departments")
    if not has_permission and not await is_admin_or_manager(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to create departments")
    
    return await create_department(db, department, current_user)

@router.get("/{department_id}", 
    response_model=DepartmentOut,
    summary="Get department by ID",
    description="Retrieve department details. Requires view_departments permission or manager/admin access."
)
async def read_department(
    department_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific department by its ID."""
    has_permission = await check_user_permission(db, current_user.user_id, "view_departments")
    if not has_permission and not await is_admin_or_manager(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to view departments")
    
    department = await get_department_by_id(db, department_id)
    if not department:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                          detail="Department not found")
    
    return department

@router.get("/", 
    response_model=List[DepartmentOut],
    summary="List all departments",
    description="Retrieve all departments with pagination. Requires view_departments permission or manager/admin access."
)
async def read_departments(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get a paginated list of all departments."""
    has_permission = await check_user_permission(db, current_user.user_id, "view_departments")
    if not has_permission and not await is_admin_or_manager(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to view departments")
    
    return await get_departments(db, skip, limit)

@router.put("/{department_id}", 
    response_model=DepartmentOut,
    summary="Update department",
    description="Update department information. Requires manage_departments permission."
)
async def update_existing_department(
    department_id: int,
    department_update: DepartmentUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Update an existing department's information."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_departments")
    if not has_permission and not await is_admin_or_manager(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to update departments")
    
    return await update_department(db, department_id, department_update, current_user)

@router.delete("/{department_id}", 
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete department",
    description="Soft delete a department. Requires manage_departments permission."
)
async def delete_existing_department(
    department_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a department from the system."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_departments")
    if not has_permission and not await is_admin_or_manager(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to delete departments")
    
    await delete_department(db, department_id)
    return None