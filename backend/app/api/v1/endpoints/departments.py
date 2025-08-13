from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timezone
from app.core.database import get_db
from app.models.departments import Departments
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.enums import Permission
from app.schemas.department import DepartmentCreate, DepartmentUpdate, DepartmentOut
from app.core.config import Settings, get_settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/departments", tags=["Departments"])

@router.post("/", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
@require_permissions([Permission.MANAGE_DEPARTMENTS])
async def create_department(
    department: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> DepartmentOut:
    """Create a new department."""
    try:
        # Check if department name already exists
        query = select(Departments).where(
            Departments.department_name == department.department_name,
            Departments.is_active == True
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Department name already exists"
            )

        db_department = Departments(
            **department.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        
        db.add(db_department)
        await db.commit()
        await db.refresh(db_department)

        logger.info(f"Created department: {db_department.department_id}")
        return DepartmentOut.model_validate(db_department)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating department: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating department"
        )

@router.get("/{department_id}", response_model=DepartmentOut)
@require_permissions([Permission.MANAGE_DEPARTMENTS])
async def get_department(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> DepartmentOut:
    """Get department by ID."""
    try:
        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        department = result.scalar_one_or_none()

        if not department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found"
            )

        return DepartmentOut.model_validate(department)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving department {department_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving department"
        )

@router.get("/", response_model=List[DepartmentOut])
@require_permissions([Permission.MANAGE_DEPARTMENTS])
async def list_departments(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[DepartmentOut]:
    """List all active departments."""
    try:
        query = select(Departments).where(
            Departments.is_active == True,
            Departments.deleted_at == None
        ).offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        
        result = await db.execute(query)
        departments = result.scalars().all()

        return [DepartmentOut.model_validate(dept) for dept in departments]

    except Exception as e:
        logger.error(f"Error retrieving departments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving departments"
        )

@router.put("/{department_id}", response_model=DepartmentOut)
@require_permissions([Permission.MANAGE_DEPARTMENTS])
async def update_department(
    department_id: int,
    department_update: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> DepartmentOut:
    """Update an existing department."""
    try:
        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        department = result.scalar_one_or_none()

        if not department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found"
            )

        update_data = department_update.model_dump(exclude_none=True)
        
        # Check for name conflicts if updating department_name
        if "department_name" in update_data and update_data["department_name"] != department.department_name:
            query = select(Departments).where(
                Departments.department_name == update_data["department_name"],
                Departments.is_active == True
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Department name already exists"
                )

        # Update fields
        for key, value in update_data.items():
            setattr(department, key, value)

        department.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(department)

        logger.info(f"Updated department: {department_id}")
        return DepartmentOut.model_validate(department)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating department {department_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating department"
        )

@router.delete("/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions([Permission.MANAGE_DEPARTMENTS])
async def delete_department(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> None:
    """Soft delete a department."""
    try:
        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        department = result.scalar_one_or_none()

        if not department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found"
            )

        department.is_active = False
        department.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Deleted department: {department_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting department {department_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting department"
        )