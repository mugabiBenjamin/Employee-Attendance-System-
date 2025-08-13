from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
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
from app.core.exceptions import ValidationError, DatabaseError, ResourceNotFoundError, ResourceConflictError
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
            raise ResourceConflictError(detail="Department name already exists")

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

    except ResourceConflictError as e:
        logger.error(f"Conflict error in create_department: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in create_department: {str(e)}")
        raise DatabaseError(message="Database error creating department", original_error=e)
    except Exception as e:
        logger.error(f"Unexpected error in create_department: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error creating department"
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
        if department_id <= 0:
            raise ValidationError(detail="Invalid department ID")

        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        department = result.scalar_one_or_none()

        if not department:
            raise ResourceNotFoundError(resource="Department", identifier=str(department_id))

        return DepartmentOut.model_validate(department)

    except ValidationError as e:
        logger.error(f"Validation error in get_department for department_id {department_id}: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_department for department_id {department_id}: {str(e)}")
        raise DatabaseError(message="Database error retrieving department", original_error=e)
    except ResourceNotFoundError as e:
        logger.error(f"Resource not found in get_department for department_id {department_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_department for department_id {department_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error retrieving department"
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
        if skip < 0 or limit <= 0:
            raise ValidationError(detail="Invalid pagination parameters")

        query = select(Departments).where(
            Departments.is_active == True,
            Departments.deleted_at == None
        ).offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        
        result = await db.execute(query)
        departments = result.scalars().all()

        return [DepartmentOut.model_validate(dept) for dept in departments]

    except ValidationError as e:
        logger.error(f"Validation error in list_departments: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in list_departments: {str(e)}")
        raise DatabaseError(message="Database error retrieving departments", original_error=e)
    except Exception as e:
        logger.error(f"Unexpected error in list_departments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error retrieving departments"
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
        if department_id <= 0:
            raise ValidationError(detail="Invalid department ID")

        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        department = result.scalar_one_or_none()

        if not department:
            raise ResourceNotFoundError(resource="Department", identifier=str(department_id))

        update_data = department_update.model_dump(exclude_none=True)
        
        if "department_name" in update_data and update_data["department_name"] != department.department_name:
            query = select(Departments).where(
                Departments.department_name == update_data["department_name"],
                Departments.is_active == True
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise ResourceConflictError(detail="Department name already exists")

        for key, value in update_data.items():
            setattr(department, key, value)

        department.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(department)

        logger.info(f"Updated department: {department_id}")
        return DepartmentOut.model_validate(department)

    except ValidationError as e:
        logger.error(f"Validation error in update_department for department_id {department_id}: {str(e)}")
        raise
    except ResourceNotFoundError as e:
        logger.error(f"Resource not found in update_department for department_id {department_id}: {str(e)}")
        raise
    except ResourceConflictError as e:
        logger.error(f"Conflict error in update_department for department_id {department_id}: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in update_department for department_id {department_id}: {str(e)}")
        raise DatabaseError(message="Database error updating department", original_error=e)
    except Exception as e:
        logger.error(f"Unexpected error in update_department for department_id {department_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error updating department"
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
        if department_id <= 0:
            raise ValidationError(detail="Invalid department ID")

        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        department = result.scalar_one_or_none()

        if not department:
            raise ResourceNotFoundError(resource="Department", identifier=str(department_id))

        department.is_active = False
        department.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Deleted department: {department_id}")

    except ValidationError as e:
        logger.error(f"Validation error in delete_department for department_id {department_id}: {str(e)}")
        raise
    except ResourceNotFoundError as e:
        logger.error(f"Resource not found in delete_department for department_id {department_id}: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in delete_department for department_id {department_id}: {str(e)}")
        raise DatabaseError(message="Database error deleting department", original_error=e)
    except Exception as e:
        logger.error(f"Unexpected error in delete_department for department_id {department_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error deleting department"
        )