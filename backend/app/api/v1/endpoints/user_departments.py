from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.utils import get_request_id
from app.services.user_department_service import (
    create_user_department as service_create_user_department,
    read_user_department as service_read_user_department,
    read_user_departments as service_read_user_departments,
    update_user_department as service_update_user_department,
    delete_user_department as service_delete_user_department,
    get_user_departments as service_get_user_departments
)
from app.schemas.user_department import UserDepartmentCreate, UserDepartmentUpdate, UserDepartmentOut
from app.core.permissions import require_permissions_dependency
from app.core.enums import Permission

router = APIRouter(prefix="/user-departments", tags=["User Departments"])

@router.post(
    "/",
    response_model=UserDepartmentOut,
    status_code=201,
    summary="Create a user-department assignment"
)
async def create_user_department_endpoint(
    user_department: UserDepartmentCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.CREATE_USER_DEPARTMENT]))
) -> UserDepartmentOut:
    """Create a new user-department assignment."""
    request_id = get_request_id(request)
    return await service_create_user_department(user_department, request, current_user, db, settings, request_id)

@router.get(
    "/{user_department_id}",
    response_model=UserDepartmentOut,
    summary="Get user-department assignment by ID"
)
async def read_user_department_endpoint(
    user_department_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.VIEW_USER_DEPARTMENT]))
) -> UserDepartmentOut:
    """Retrieve a user-department assignment by ID."""
    request_id = get_request_id(request)
    return await service_read_user_department(user_department_id, db, request_id)

@router.get(
    "/",
    response_model=List[UserDepartmentOut],
    summary="List user-department assignments"
)
async def read_user_departments_endpoint(
    request: Request,
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_USER_DEPARTMENT]))
) -> List[UserDepartmentOut]:
    """List user-department assignments with optional filters and pagination."""
    request_id = get_request_id(request)
    return await service_read_user_departments(user_id, department_id, skip, limit, current_user, db, settings, request_id)

@router.put(
    "/{user_department_id}",
    response_model=UserDepartmentOut,
    summary="Update a user-department assignment"
)
async def update_user_department_endpoint(
    user_department_id: int,
    user_department_update: UserDepartmentUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.UPDATE_USER_DEPARTMENT]))
) -> UserDepartmentOut:
    """Update a user-department assignment."""
    request_id = get_request_id(request)
    return await service_update_user_department(user_department_id, user_department_update, request, current_user, db, settings, request_id)

@router.delete(
    "/{user_department_id}",
    status_code=204,
    summary="Delete a user-department assignment"
)
async def delete_user_department_endpoint(
    user_department_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.DELETE_USER_DEPARTMENT]))
) -> None:
    """Soft delete a user-department assignment."""
    request_id = get_request_id(request)
    await service_delete_user_department(user_department_id, request, current_user, db, settings, request_id)

@router.get(
    "/user/{user_id}/departments",
    response_model=List[UserDepartmentOut],
    summary="Get all departments for a user"
)
async def get_user_departments_endpoint(
    user_id: int,
    request: Request,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_USER_DEPARTMENT]))
) -> List[UserDepartmentOut]:
    """Retrieve all department assignments for a specific user with pagination."""
    request_id = get_request_id(request)
    return await service_get_user_departments(user_id, skip, limit, current_user, db, settings, request_id)