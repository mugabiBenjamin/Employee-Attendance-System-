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
from app.core.permissions import check_permissions
from app.core.security import get_current_active_user
from app.core.config import settings
from app.core.enums import Permission
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

async def is_admin_or_hr(db: AsyncSession, user: Users) -> bool:
    """Check if user has HR, Admin, or Super_Admin role."""
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

@router.post("/", response_model=UserDepartmentOut, status_code=status.HTTP_201_CREATED, summary="Create user department assignment")
async def create_user_department(
    user_department: UserDepartmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserDepartmentOut:
    """Create a new user department assignment."""
    try:
        has_permission = await check_permissions([Permission.MANAGE_USER_DEPARTMENTS.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create user department assignments")

        # Verify user exists
        query = select(Users).where(Users.user_id == user_department.user_id, Users.is_active == True, Users.deleted_at == None)
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Verify department exists
        query = select(Departments).where(Departments.department_id == user_department.department_id, Departments.is_active == True, Departments.deleted_at == None)
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

@router.get("/{assignment_id}", response_model=UserDepartmentOut, summary="Get user department assignment by ID")
async def read_user_department(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserDepartmentOut:
    """Get a specific user department assignment by ID."""
    try:
        has_permission = await check_permissions([Permission.VIEW_USER_DEPARTMENTS.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view user department assignments")

        query = select(UserDepartments).where(UserDepartments.assignment_id == assignment_id, UserDepartments.is_active == True, UserDepartments.deleted_at == None)
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

@router.get("/", response_model=List[UserDepartmentOut], summary="List user department assignments")
async def read_user_departments(
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[UserDepartmentOut]:
    """Get a paginated list of user department assignments."""
    try:
        has_permission = await check_permissions([Permission.VIEW_USER_DEPARTMENTS.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view user department assignments")

        query = select(UserDepartments).where(UserDepartments.is_active == True, UserDepartments.deleted_at == None)
        if user_id:
            query = query.where(UserDepartments.user_id == user_id)
        if department_id:
            query = query.where(UserDepartments.department_id == user_id)
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

@router.put("/{assignment_id}", response_model=UserDepartmentOut, summary="Update user department assignment")
async def update_user_department(
    assignment_id: int,
    user_department_update: UserDepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserDepartmentOut:
    """Update an existing user department assignment."""
    try:
        has_permission = await check_permissions([Permission.MANAGE_USER_DEPARTMENTS.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update user department assignments")

        query = select(UserDepartments).where(UserDepartments.assignment_id == assignment_id, UserDepartments.is_active == True, UserDepartments.deleted_at == None)
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()

        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User department assignment not found")

        update_data = user_department_update.model_dump(exclude_none=True)
        if "user_id" in update_data:
            query = select(Users).where(Users.user_id == update_data["user_id"], Users.is_active == True, Users.deleted_at == None)
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if "department_id" in update_data:
            query = select(Departments).where(Departments.department_id == update_data["department_id"], Departments.is_active == True, Departments.deleted_at == None)
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

@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete user department assignment")
async def delete_user_department(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    """Soft delete a user department assignment."""
    try:
        has_permission = await check_permissions([Permission.MANAGE_USER_DEPARTMENTS.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete user department assignments")

        query = select(UserDepartments).where(UserDepartments.assignment_id == assignment_id, UserDepartments.is_active == True, UserDepartments.deleted_at == None)
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