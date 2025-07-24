from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict
from app.models.departments import Departments
from app.models.users import Users
from app.schemas.department import DepartmentCreate, DepartmentUpdate, DepartmentOut
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class DepartmentCreateInternal(BaseModel):
    department_name: str
    description: Optional[str] = None
    manager_id: Optional[int] = None
    budget: Optional[float] = None
    location: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

async def create_department(db: AsyncSession, department: DepartmentCreate, current_user: Users) -> DepartmentOut:
    """
    Create a new department with validation and logging.
    """
    try:
        # Check for existing department name
        query = select(Departments).where(Departments.department_name == department.department_name)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Department name already exists"
            )

        # Validate manager_id if provided
        if department.manager_id:
            query = select(Users).where(
                Users.user_id == department.manager_id,
                Users.is_active == True,
                Users.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Manager not found"
                )

        # Create department
        db_department = Departments(
            **DepartmentCreateInternal(**department.model_dump()).model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_department)
        await db.commit()
        await db.refresh(db_department)

        logger.info(f"Department created, department_id: {db_department.department_id}, name: {db_department.department_name}")
        return DepartmentOut.model_validate(db_department)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating department: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating department"
        )

async def get_department_by_id(db: AsyncSession, department_id: int) -> Optional[DepartmentOut]:
    """
    Retrieve a department by ID.
    """
    try:
        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        department = result.scalar_one_or_none()

        if not department:
            return None

        return DepartmentOut.model_validate(department)

    except Exception as e:
        logger.error(f"Error retrieving department {department_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving department"
        )

async def get_departments(db: AsyncSession, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[DepartmentOut]:
    """
    Retrieve a list of active departments with pagination.
    """
    try:
        query = select(Departments).where(
            Departments.is_active == True,
            Departments.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        departments = result.scalars().all()

        logger.info(f"Retrieved {len(departments)} departments")
        return [DepartmentOut.model_validate(dept) for dept in departments]

    except Exception as e:
        logger.error(f"Error retrieving departments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving departments"
        )

async def update_department(db: AsyncSession, department_id: int, department_update: DepartmentUpdate, current_user: Users) -> DepartmentOut:
    """
    Update a department with validation and logging.
    """
    try:
        # Retrieve department
        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        db_department = result.scalar_one_or_none()

        if not db_department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found"
            )

        # Check for duplicate department name
        update_data = department_update.model_dump(exclude_none=True)
        if "department_name" in update_data:
            query = select(Departments).where(
                Departments.department_name == update_data["department_name"],
                Departments.department_id != department_id
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Department name already exists"
                )

        # Validate manager_id if provided
        if "manager_id" in update_data and update_data["manager_id"]:
            query = select(Users).where(
                Users.user_id == update_data["manager_id"],
                Users.is_active == True,
                Users.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Manager not found"
                )

        # Apply updates
        for key, value in update_data.items():
            setattr(db_department, key, value)

        db_department.updated_at = datetime.now(timezone.utc)
        db.add(db_department)
        await db.commit()
        await db.refresh(db_department)

        logger.info(f"Department updated, department_id: {department_id}")
        return DepartmentOut.model_validate(db_department)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating department {department_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating department"
        )

async def delete_department(db: AsyncSession, department_id: int, current_user: Users) -> None:
    """
    Soft delete a department with logging.
    """
    try:
        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        db_department = result.scalar_one_or_none()

        if not db_department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found"
            )

        db_department.is_active = False
        db_department.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Department soft deleted, department_id: {department_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting department {department_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting department"
        )