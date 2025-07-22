from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.user import (
    UserCreate, UserUpdate, UserOut, 
    UserDepartmentCreate, UserDepartmentOut, 
    EmployeeHierarchyCreate, EmployeeHierarchyOut, 
    EmployeeEmergencyContactCreate, EmployeeEmergencyContactOut
)
from app.services.user_service import (
    create_user, update_user, delete_user, 
    get_user_by_id, get_users, 
    create_user_department, create_employee_hierarchy, 
    create_employee_emergency_contact
)
from app.api.deps import get_db_session, get_current_active_user
from app.services.auth_service import check_user_permission
from app.models.user import User
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

async def is_admin(db: AsyncSession, user: User) -> bool:
    from sqlmodel import select
    from app.models.user_roles import UserRole
    from app.models.user_roles import Role
    query = select(User).join(UserRole).join(Role).where(
        User.user_id == user.user_id,
        UserRole.is_active == True,
        Role.role_name.in_(["Admin", "Super_Admin"])
    )
    result = await db.execute(query)
    return result.scalar_one_or_none() is not None

@router.post("/", 
    response_model=UserOut, 
    status_code=status.HTTP_201_CREATED,
    summary="Create new user",
    description="Create a new user account with department assignment and employee type validation."
)
async def create_new_user(
    user: UserCreate,
    department_id: Optional[int] = None,
    manager_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new user in the system."""
    has_permission = await check_user_permission(db, current_user.user_id, "create_user")
    if not has_permission and not await is_admin(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to create users")
    
    valid_employee_types = ["full_time", "part_time", "contract", "intern", "temporary"]
    if user.employee_type not in valid_employee_types:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                          detail=f"Invalid employee type. Must be one of {valid_employee_types}")
    
    return await create_user(db, user, department_id, manager_id)

@router.get("/{user_id}", 
    response_model=UserOut,
    summary="Get user by ID",
    description="Retrieve user details. Users can view their own profile, admins or those with view_users permission can view any user."
)
async def read_user(
    user_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific user by their ID."""
    has_permission = await check_user_permission(db, current_user.user_id, "view_users")
    if current_user.user_id != user_id and not has_permission and not await is_admin(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to view this user")
    
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                          detail="User not found")
    
    return UserOut.model_validate(user)

@router.get("/", 
    response_model=List[UserOut],
    summary="List all users",
    description="Retrieve all users with pagination. Requires view_users permission or admin access."
)
async def read_users(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get a paginated list of all users."""
    has_permission = await check_user_permission(db, current_user.user_id, "view_users")
    if not has_permission and not await is_admin(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to view users")
    
    return await get_users(db, skip, limit)

@router.put("/{user_id}", 
    response_model=UserOut,
    summary="Update user",
    description="Update user information including department and hierarchy. Requires update_users permission or admin access."
)
async def update_existing_user(
    user_id: int,
    user_update: UserUpdate,
    department_id: Optional[int] = None,
    manager_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Update an existing user's information."""
    has_permission = await check_user_permission(db, current_user.user_id, "update_users")
    if current_user.user_id != user_id and not has_permission and not await is_admin(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to update this user")
    
    if user_update.employee_type:
        valid_employee_types = ["full_time", "part_time", "contract", "intern", "temporary"]
        if user_update.employee_type not in valid_employee_types:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"Invalid employee type. Must be one of {valid_employee_types}")
    
    return await update_user(db, user_id, user_update, department_id, manager_id)

@router.delete("/{user_id}", 
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Soft delete a user account. Requires delete_users permission or admin access."
)
async def delete_existing_user(
    user_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a user from the system."""
    has_permission = await check_user_permission(db, current_user.user_id, "delete_users")
    if not has_permission and not await is_admin(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to delete users")
    
    await delete_user(db, user_id)
    return None

@router.post("/department", 
    response_model=UserDepartmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Assign user to department",
    description="Assign a user to a department. Requires manage_departments permission."
)
async def assign_user_department(
    user_department: UserDepartmentCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Assign a user to a department."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_departments")
    if not has_permission and not await is_admin(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to assign departments")
    
    return await create_user_department(db, user_department)

@router.post("/hierarchy", 
    response_model=EmployeeHierarchyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create employee hierarchy",
    description="Create an employee hierarchy entry. Requires manage_hierarchy permission."
)
async def create_hierarchy(
    hierarchy: EmployeeHierarchyCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Create an employee hierarchy entry."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_hierarchy")
    if not has_permission and not await is_admin(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to manage hierarchy")
    
    return await create_employee_hierarchy(db, hierarchy)

@router.post("/emergency-contact", 
    response_model=EmployeeEmergencyContactOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create emergency contact",
    description="Create an emergency contact for a user. Users can create their own contacts, admins or those with manage_emergency_contacts permission can create for others."
)
async def create_emergency_contact(
    contact: EmployeeEmergencyContactCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Create an emergency contact for a user."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_emergency_contacts")
    if contact.user_id != current_user.user_id and not has_permission and not await is_admin(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to create emergency contacts for this user")
    
    return await create_employee_emergency_contact(db, contact)