from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict
from app.models.user_departments import UserDepartments
from app.models.users import Users
from app.models.departments import Departments
from app.models.system_logs import SystemLogs
from app.core.config import settings
from app.core.enums import SystemAction
import logging

logger = logging.getLogger(__name__)

class UserDepartmentCreateInternal(BaseModel):
    user_id: int
    department_id: int
    is_primary: bool = False

    model_config = ConfigDict(from_attributes=True)

class UserDepartmentUpdateInternal(BaseModel):
    department_id: Optional[int] = None
    is_primary: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)

class UserDepartmentOut(BaseModel):
    user_department_id: int
    user_id: int
    department_id: int
    is_primary: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

async def create_user_department(db: AsyncSession, user_department: UserDepartmentCreateInternal, current_user: Users) -> UserDepartmentOut:
    """
    Assign a user to a department with validation and logging.
    """
    try:
        # Validate user
        query = select(Users).where(
            Users.user_id == user_department.user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Validate department
        query = select(Departments).where(
            Departments.department_id == user_department.department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found"
            )

        # Check for existing assignment
        query = select(UserDepartments).where(
            UserDepartments.user_id == user_department.user_id,
            UserDepartments.department_id == user_department.department_id,
            UserDepartments.is_active == True,
            UserDepartments.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already assigned to this department"
            )

        # If setting as primary, update existing primary assignments
        if user_department.is_primary:
            query = select(UserDepartments).where(
                UserDepartments.user_id == user_department.user_id,
                UserDepartments.is_primary == True,
                UserDepartments.is_active == True,
                UserDepartments.deleted_at == None
            )
            result = await db.execute(query)
            existing_primary = result.scalars().all()
            for primary in existing_primary:
                primary.is_primary = False
                db.add(primary)

        # Create user-department assignment
        db_user_department = UserDepartments(
            **user_department.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_user_department)
        await db.commit()
        await db.refresh(db_user_department)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.ASSIGN_DEPARTMENT,
            table_affected="user_departments",
            record_id=db_user_department.user_department_id,
            old_values=None,
            new_values=db_user_department.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"User department assignment created, user_department_id: {db_user_department.user_department_id}, user_id: {user_department.user_id}")
        return UserDepartmentOut.model_validate(db_user_department)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user department assignment for user_id {user_department.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating user department assignment"
        )

async def get_user_department_by_id(db: AsyncSession, user_department_id: int) -> Optional[UserDepartmentOut]:
    """
    Retrieve a user-department assignment by ID.
    """
    try:
        query = select(UserDepartments).where(
            UserDepartments.user_department_id == user_department_id,
            UserDepartments.is_active == True,
            UserDepartments.deleted_at == None
        )
        result = await db.execute(query)
        user_department = result.scalar_one_or_none()

        if not user_department:
            return None

        return UserDepartmentOut.model_validate(user_department)

    except Exception as e:
        logger.error(f"Error retrieving user department assignment {user_department_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving user department assignment"
        )

async def get_user_departments(db: AsyncSession, user_id: int, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[UserDepartmentOut]:
    """
    Retrieve a list of department assignments for a user with pagination.
    """
    try:
        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        query = select(UserDepartments).where(
            UserDepartments.user_id == user_id,
            UserDepartments.is_active == True,
            UserDepartments.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        user_departments = result.scalars().all()

        logger.info(f"Retrieved {len(user_departments)} department assignments for user_id: {user_id}")
        return [UserDepartmentOut.model_validate(ud) for ud in user_departments]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving department assignments for user_id {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving department assignments"
        )

async def update_user_department(db: AsyncSession, user_department_id: int, user_department_update: UserDepartmentUpdateInternal, current_user: Users) -> UserDepartmentOut:
    """
    Update a user-department assignment with validation and logging.
    """
    try:
        # Retrieve user-department assignment
        query = select(UserDepartments).where(
            UserDepartments.user_department_id == user_department_id,
            UserDepartments.is_active == True,
            UserDepartments.deleted_at == None
        )
        result = await db.execute(query)
        db_user_department = result.scalar_one_or_none()

        if not db_user_department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User department assignment not found"
            )

        # Validate department if updated
        update_data = user_department_update.model_dump(exclude_none=True)
        if "department_id" in update_data:
            query = select(Departments).where(
                Departments.department_id == update_data["department_id"],
                Departments.is_active == True,
                Departments.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Department not found"
                )

            # Check for existing assignment
            query = select(UserDepartments).where(
                UserDepartments.user_id == db_user_department.user_id,
                UserDepartments.department_id == update_data["department_id"],
                UserDepartments.user_department_id != user_department_id,
                UserDepartments.is_active == True,
                UserDepartments.deleted_at == None
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User is already assigned to this department"
                )

        # If setting as primary, update existing primary assignments
        if "is_primary" in update_data and update_data["is_primary"]:
            query = select(UserDepartments).where(
                UserDepartments.user_id == db_user_department.user_id,
                UserDepartments.is_primary == True,
                UserDepartments.user_department_id != user_department_id,
                UserDepartments.is_active == True,
                UserDepartments.deleted_at == None
            )
            result = await db.execute(query)
            existing_primary = result.scalars().all()
            for primary in existing_primary:
                primary.is_primary = False
                db.add(primary)

        # Store old values for logging
        old_values = db_user_department.__dict__.copy()

        # Apply updates
        for key, value in update_data.items():
            setattr(db_user_department, key, value)

        db_user_department.updated_at = datetime.now(timezone.utc)
        db.add(db_user_department)
        await db.commit()
        await db.refresh(db_user_department)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_DEPARTMENT_ASSIGNMENT,
            table_affected="user_departments",
            record_id=user_department_id,
            old_values=old_values,
            new_values=db_user_department.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"User department assignment updated, user_department_id: {user_department_id}")
        return UserDepartmentOut.model_validate(db_user_department)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user department assignment {user_department_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating user department assignment"
        )

async def delete_user_department(db: AsyncSession, user_department_id: int, current_user: Users) -> None:
    """
    Soft delete a user-department assignment with logging.
    """
    try:
        query = select(UserDepartments).where(
            UserDepartments.user_department_id == user_department_id,
            UserDepartments.is_active == True,
            UserDepartments.deleted_at == None
        )
        result = await db.execute(query)
        db_user_department = result.scalar_one_or_none()

        if not db_user_department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User department assignment not found"
            )

        db_user_department.is_active = False
        db_user_department.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_DEPARTMENT_ASSIGNMENT,
            table_affected="user_departments",
            record_id=user_department_id,
            old_values=db_user_department.__dict__,
            new_values=None,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"User department assignment soft deleted, user_department_id: {user_department_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user department assignment {user_department_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting user department assignment"
        )