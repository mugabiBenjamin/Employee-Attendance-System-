from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import AsyncGenerator, List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone
from app.core.database import AsyncSessionLocal
from app.models.departments import Departments
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.models.users import Users
from app.core.config import settings
from app.core.security import check_user_permission
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/departments", tags=["Departments"])

class DepartmentCreate(BaseModel):
    """Schema for creating a new department."""
    name: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class DepartmentUpdate(BaseModel):
    """Schema for updating an existing department."""
    name: Optional[str] = None
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class DepartmentOut(BaseModel):
    """Schema for department output."""
    department_id: int
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to provide an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {str(e)}")
            await session.rollback()
            raise
        finally:
            await session.close()

async def get_current_active_user(db: AsyncSession = Depends(get_db)) -> Users:
    """Dependency to get the current active user."""
    # This is a placeholder. In a real implementation, this would verify the JWT token
    # and fetch the user from the database. For this example, we assume it's provided.
    query = select(Users).where(Users.is_active == True, Users.deleted_at == None)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")
    return user

async def is_admin_or_manager(db: AsyncSession, user: Users) -> bool:
    """
    Check if the user has Manager, HR, Admin, or Super_Admin role.

    Args:
        db: Async database session.
        user: Current user object.

    Returns:
        bool: True if user has required role, False otherwise.
    """
    try:
        query = select(UserRoles).join(Roles).where(
            UserRoles.user_id == user.user_id,
            UserRoles.is_active == True,
            Roles.role_name.in_(["Manager", "HR", "Admin", "Super_Admin"]),
            Roles.is_active == True
        )
        result = await db.execute(query)
        return result.scalar_one_or_none() is not None
    except Exception as e:
        logger.error(f"Error checking admin/manager role for user_id {user.user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error checking user role")

@router.post("/", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED, summary="Create new department", description="Create a new department. Requires manage_departments permission.")
async def create_new_department(
    department: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> DepartmentOut:
    """
    Create a new department in the system.

    Args:
        department: Department creation data.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        DepartmentOut: Created department details.

    Raises:
        HTTPException: If user lacks permission or department name already exists.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "manage_departments")
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create departments")

        query = select(Departments).where(Departments.name == department.name, Departments.is_active == True)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department name already exists")

        db_department = Departments(
            **department.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_department)
        await db.commit()
        await db.refresh(db_department)

        logger.info(f"Department created, department_id: {db_department.department_id}, name: {db_department.name}")
        return DepartmentOut.model_validate(db_department)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating department: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating department")

@router.get("/{department_id}", response_model=DepartmentOut, summary="Get department by ID", description="Retrieve department details. Requires view_departments permission or manager/admin access.")
async def read_department(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> DepartmentOut:
    """
    Get a specific department by its ID.

    Args:
        department_id: ID of the department to retrieve.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        DepartmentOut: Department details.

    Raises:
        HTTPException: If user lacks permission or department not found.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "view_departments")
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view departments")

        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        department = result.scalar_one_or_none()

        if not department:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

        logger.info(f"Retrieved department, department_id: {department_id}")
        return DepartmentOut.model_validate(department)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving department {department_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving department")

@router.get("/", response_model=List[DepartmentOut], summary="List all departments", description="Retrieve all departments with pagination. Requires view_departments permission or manager/admin access.")
async def read_departments(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[DepartmentOut]:
    """
    Get a paginated list of all departments.

    Args:
        skip: Number of records to skip (for pagination).
        limit: Maximum number of records to return.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        List[DepartmentOut]: List of department details.

    Raises:
        HTTPException: If user lacks permission.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "view_departments")
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view departments")

        query = select(Departments).where(
            Departments.is_active == True,
            Departments.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        departments = result.scalars().all()

        logger.info(f"Retrieved {len(departments)} departments")
        return [DepartmentOut.model_validate(dept) for dept in departments]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving departments: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving departments")

@router.put("/{department_id}", response_model=DepartmentOut, summary="Update department", description="Update department information. Requires manage_departments permission.")
async def update_existing_department(
    department_id: int,
    department_update: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> DepartmentOut:
    """
    Update an existing department's information.

    Args:
        department_id: ID of the department to update.
        department_update: Updated department data.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        DepartmentOut: Updated department details.

    Raises:
        HTTPException: If user lacks permission, department not found, or name already exists.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "manage_departments")
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update departments")

        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        department = result.scalar_one_or_none()

        if not department:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

        update_data = department_update.model_dump(exclude_none=True)
        if "name" in update_data and update_data["name"] != department.name:
            query = select(Departments).where(Departments.name == update_data["name"], Departments.is_active == True)
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department name already exists")

        for key, value in update_data.items():
            setattr(department, key, value)

        department.updated_at = datetime.now(timezone.utc)
        db.add(department)
        await db.commit()
        await db.refresh(department)

        logger.info(f"Department updated, department_id: {department_id}")
        return DepartmentOut.model_validate(department)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating department {department_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating department")

@router.delete("/{department_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete department", description="Soft delete a department. Requires manage_departments permission.")
async def delete_existing_department(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    """
    Soft delete a department from the system.

    Args:
        department_id: ID of the department to delete.
        db: Async database session.
        current_user: Current authenticated user.

    Raises:
        HTTPException: If user lacks permission or department not found.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "manage_departments")
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete departments")

        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        department = result.scalar_one_or_none()

        if not department:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

        department.is_active = False
        department.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Department soft deleted, department_id: {department_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting department {department_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting department")