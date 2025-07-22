from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from datetime import datetime, timezone
from app.models.departments import Department
from app.models.user import User
from app.schemas.user import DepartmentCreate, DepartmentUpdate, DepartmentOut
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

async def create_department(db: AsyncSession, department_create: DepartmentCreate, current_user: User) -> DepartmentOut:
    try:
        # Check if department already exists
        query = select(Department).where(Department.department_name == department_create.department_name)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="Department name already exists")
        
        # Validate manager_id if provided
        if department_create.manager_id:
            manager = await db.execute(
                select(User).where(User.user_id == department_create.manager_id, 
                                 User.is_active == True, 
                                 User.deleted_at == None)
            )
            if not manager.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                                  detail="Manager not found")
        
        # Validate budget
        if department_create.budget is not None and department_create.budget < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="Budget cannot be negative")
        
        db_department = Department(
            **department_create.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_department)
        await db.commit()
        await db.refresh(db_department)
        
        logger.info(f"Department created, department_id {db_department.department_id}")
        return DepartmentOut.model_validate(db_department)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating department: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error creating department")

async def get_department_by_id(db: AsyncSession, department_id: int) -> Optional[DepartmentOut]:
    try:
        query = select(Department).where(Department.department_id == department_id, 
                                      Department.is_active == True, 
                                      Department.deleted_at == None)
        result = await db.execute(query)
        department = result.scalar_one_or_none()
        
        if not department:
            return None
        
        return DepartmentOut.model_validate(department)
    except Exception as e:
        logger.error(f"Error retrieving department: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error retrieving department")

async def get_departments(db: AsyncSession, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[DepartmentOut]:
    try:
        query = select(Department).where(Department.is_active == True, 
                                      Department.deleted_at == None).offset(skip).limit(limit)
        result = await db.execute(query)
        departments = result.scalars().all()
        
        logger.info(f"Retrieved {len(departments)} departments")
        return [DepartmentOut.model_validate(dept) for dept in departments]
    except Exception as e:
        logger.error(f"Error retrieving departments: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error retrieving departments")

async def update_department(db: AsyncSession, department_id: int, department_update: DepartmentUpdate, 
                          current_user: User) -> DepartmentOut:
    try:
        query = select(Department).where(Department.department_id == department_id, 
                                      Department.is_active == True, 
                                      Department.deleted_at == None)
        result = await db.execute(query)
        department = result.scalar_one_or_none()
        
        if not department:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                              detail="Department not found")
        
        update_data = department_update.model_dump(exclude_none=True)
        
        # Validate department_name if provided
        if "department_name" in update_data:
            query = select(Department).where(
                Department.department_name == update_data["department_name"],
                Department.department_id != department_id
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                                  detail="Department name already exists")
        
        # Validate manager_id if provided
        if "manager_id" in update_data and update_data["manager_id"]:
            manager = await db.execute(
                select(User).where(User.user_id == update_data["manager_id"], 
                                 User.is_active == True, 
                                 User.deleted_at == None)
            )
            if not manager.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                                  detail="Manager not found")
        
        # Validate budget if provided
        if "budget" in update_data and update_data["budget"] is not None and update_data["budget"] < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="Budget cannot be negative")
        
        for key, value in update_data.items():
            setattr(department, key, value)
        
        department.updated_at = datetime.now(timezone.utc)
        db.add(department)
        await db.commit()
        await db.refresh(department)
        
        logger.info(f"Department updated, department_id {department_id}")
        return DepartmentOut.model_validate(department)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating department: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error updating department")

async def delete_department(db: AsyncSession, department_id: int) -> None:
    try:
        query = select(Department).where(Department.department_id == department_id, 
                                      Department.is_active == True, 
                                      Department.deleted_at == None)
        result = await db.execute(query)
        department = result.scalar_one_or_none()
        
        if not department:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                              detail="Department not found")
        
        department.is_active = False
        department.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        
        logger.info(f"Department soft deleted, department_id {department_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting department: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error deleting department")