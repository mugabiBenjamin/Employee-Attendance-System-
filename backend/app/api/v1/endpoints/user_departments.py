from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, AsyncGenerator
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone
from app.core.database import AsyncSessionLocal
from app.models.user_departments import UserDepartments
from app.models.users import Users
from app.models.departments import Departments
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.core.security import check_user_permission
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-departments", tags=["User Departments"])

class UserDepartmentCreate(BaseModel):
    """Schema for creating a new user department assignment."""
    user_id: int
    department_id: int

    model_config = ConfigDict(from_attributes=True)

class UserDepartmentUpdate(BaseModel):
    """Schema for updating an existing user department assignment."""
    user_id: Optional[int] = None
    department_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class UserDepartmentOut(BaseModel):
    """Schema for user department assignment output."""
    assignment_id: int
    user_id: int
    department_id: int
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
    query = select(Users).where(Users.is_active == True, Users.deleted_at == None)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")
    return user

async def is_admin_or_hr(db: AsyncSession, user: Users) -> bool:
    """
    Check if the user has HR, Admin, or Super_Admin role.

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
            Roles.role_name.in_(["HR", "Admin", "Super_Admin"]),
            Roles.is_active == True
        )
        result = await db.execute(query)
        return result.scalar_one_or_none() is not None
    except Exception as e:
        logger.error(f"Error checking admin/hr role for user_id {user.user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error checking user role")

@router.post("/", response_model=UserDepartmentOut, status_code=status.HTTP_201_CREATED, summary="Create user department assignment", description="Create a new user department assignment. Requires manage_user_departments permission or HR/admin access.")
async def create_user_department(
    user_department: UserDepartmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserDepartmentOut:
    """
    Create a new user department assignment in the system.

    Args:
        user_department: User department assignment creation data.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        UserDepartmentOut: Created user department assignment details.

    Raises:
        HTTPException: If user lacks permission, user/department not found, or assignment exists.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "manage_user_departments")
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create user department assignments")

        # Verify user exists
        query = select(Users).where(
            Users.user_id == user_department.user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Verify department exists
        query = select(Departments).where(
            Departments.department_id == user_department.department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

        # Check for existing assignment
        query = select(UserDepartments).where(
            UserDepartments.user_id == user_department.user_id,
            UserDepartments.department_id == user_department.department_id,
            UserDepartments.is_active == True
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User department assignment already exists")

        db_assignment = UserDepartments(
            **user_department.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_assignment)
        await db.commit()
        await db.refresh(db_assignment)

        logger.info(f"User department assignment created, assignment_id: {db_assignment.assignment_id}, user_id: {db_assignment.user_id}")
        return UserDepartmentOut.model_validate(db_assignment)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user department assignment: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating user department assignment")

@router.get("/{assignment_id}", response_model=UserDepartmentOut, summary="Get user department assignment by ID", description="Retrieve user department assignment details. Requires view_user_departments permission or HR/admin access.")
async def read_user_department(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserDepartmentOut:
    """
    Get a specific user department assignment by its ID.

    Args:
        assignment_id: ID of the user department assignment to retrieve.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        UserDepartmentOut: User department assignment details.

    Raises:
        HTTPException: If user lacks permission or assignment not found.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "view_user_departments")
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view user department assignments")

        query = select(UserDepartments).where(
            UserDepartments.assignment_id == assignment_id,
            UserDepartments.is_active == True,
            UserDepartments.deleted_at == None
        )
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()

        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User department assignment not found")

        logger.info(f"Retrieved user department assignment, assignment_id: {assignment_id}")
        return UserDepartmentOut.model_validate(assignment)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user department assignment {assignment_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving user department assignment")

@router.get("/", response_model=List[UserDepartmentOut], summary="List user department assignments", description="Retrieve all user department assignments with pagination. Requires view_user_departments permission or HR/admin access.")
async def read_user_departments(
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[UserDepartmentOut]:
    """
    Get a paginated list of user department assignments, optionally filtered by user or department.

    Args:
        user_id: Optional user ID to filter assignments.
        department_id: Optional department ID to filter assignments.
        skip: Number of records to skip (for pagination).
        limit: Maximum number of records to return.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        List[UserDepartmentOut]: List of user department assignment details.

    Raises:
        HTTPException: If user lacks permission or an error occurs.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "view_user_departments")
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view user department assignments")

        query = select(UserDepartments).where(
            UserDepartments.is_active == True,
            UserDepartments.deleted_at == None
        )
        if user_id:
            query = query.where(UserDepartments.user_id == user_id)
        if department_id:
            query = query.where(UserDepartments.department_id == department_id)
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        assignments = result.scalars().all()

        logger.info(f"Retrieved {len(assignments)} user department assignments")
        return [UserDepartmentOut.model_validate(assignment) for assignment in assignments]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user department assignments: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving user department assignments")

@router.put("/{assignment_id}", response_model=UserDepartmentOut, summary="Update user department assignment", description="Update user department assignment information. Requires manage_user_departments permission or HR/admin access.")
async def update_user_department(
    assignment_id: int,
    user_department_update: UserDepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserDepartmentOut:
    """
    Update an existing user department assignment's information.

    Args:
        assignment_id: ID of the user department assignment to update.
        user_department_update: Updated user department assignment data.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        UserDepartmentOut: Updated user department assignment details.

    Raises:
        HTTPException: If user lacks permission, assignment not found, or conflicts exist.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "manage_user_departments")
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update user department assignments")

        query = select(UserDepartments).where(
            UserDepartments.assignment_id == assignment_id,
            UserDepartments.is_active == True,
            UserDepartments.deleted_at == None
        )
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()

        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User department assignment not found")

        update_data = user_department_update.model_dump(exclude_none=True)
        if "user_id" in update_data:
            query = select(Users).where(
                Users.user_id == update_data["user_id"],
                Users.is_active == True,
                Users.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if "department_id" in update_data:
            query = select(Departments).where(
                Departments.department_id == update_data["department_id"],
                Departments.is_active == True,
                Departments.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

        if update_data.get("user_id") or update_data.get("department_id"):
            query = select(UserDepartments).where(
                UserDepartments.user_id == update_data.get("user_id", assignment.user_id),
                UserDepartments.department_id == update_data.get("department_id", assignment.department_id),
                UserDepartments.is_active == True,
                UserDepartments.assignment_id != assignment_id
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User department assignment already exists")

        for key, value in update_data.items():
            setattr(assignment, key, value)

        assignment.updated_at = datetime.now(timezone.utc)
        db.add(assignment)
        await db.commit()
        await db.refresh(assignment)

        logger.info(f"User department assignment updated, assignment_id: {assignment_id}")
        return UserDepartmentOut.model_validate(assignment)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user department assignment {assignment_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating user department assignment")

@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete user department assignment", description="Soft delete a user department assignment. Requires manage_user_departments permission or HR/admin access.")
async def delete_user_department(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    """
    Soft delete a user department assignment from the system.

    Args:
        assignment_id: ID of the user department assignment to delete.
        db: Async database session.
        current_user: Current authenticated user.

    Raises:
        HTTPException: If user lacks permission or assignment not found.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "manage_user_departments")
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete user department assignments")

        query = select(UserDepartments).where(
            UserDepartments.assignment_id == assignment_id,
            UserDepartments.is_active == True,
            UserDepartments.deleted_at == None
        )
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()

        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User department assignment not found")

        assignment.is_active = False
        assignment.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"User department assignment soft deleted, assignment_id: {assignment_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user department assignment {assignment_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting user department assignment")