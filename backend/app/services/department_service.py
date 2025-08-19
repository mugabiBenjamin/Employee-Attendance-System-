from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.departments import Departments
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.schemas.department import DepartmentCreate, DepartmentUpdate, DepartmentOut
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import DepartmentNotFoundError, ValidationError, UserNotFoundError, BusinessLogicError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_user_exists, validate_department_not_assigned
import logging

logger = logging.getLogger(__name__)

async def create_department(
    department: DepartmentCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.CREATE_DEPARTMENT]))
) -> DepartmentOut:
    """Create a new department with validation, logging, and cache clearing."""
    try:
        # Validate department name uniqueness
        query = select(Departments).where(
            Departments.department_name == department.department_name,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ValidationError(detail="Department name already exists")

        # Validate manager_id if provided
        if department.manager_id:
            await validate_user_exists(db, department.manager_id, request_id)

        db_department = Departments(
            **department.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_department)
        await db.commit()
        await db.refresh(db_department)

        # Invalidate cache
        await invalidate_cache_prefix("department")
        logger.debug(f"Cache cleared for department")

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_DEPARTMENT,
            table_affected="departments",
            record_id=db_department.department_id,
            old_values=None,
            new_values=db_department.__dict__,
            ip_address=str(request.client.host),
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc),
            request_id=request_id
        )
        db.add(system_log)
        await db.commit()

        logger.info(
            f"Department created, department_id: {db_department.department_id}, name: {db_department.department_name}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return DepartmentOut.model_validate(db_department)

    except ValidationError as e:
        logger.error(f"Validation error creating department: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"Manager not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating department: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_department(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_DEPARTMENT]))
) -> DepartmentOut:
    """Retrieve a department by ID."""
    try:
        cache_key = f"department:{department_id}"
        cached_department = await get_cache(cache_key)
        if cached_department:
            return DepartmentOut(**cached_department)

        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        department = result.scalar_one_or_none()

        if not department:
            raise DepartmentNotFoundError(dept_id=department_id)

        department_dict = DepartmentOut.model_validate(department).model_dump()
        await set_cache(cache_key, department_dict, ttl=300)

        logger.info(
            f"Retrieved department, department_id: {department_id}",
            extra={"request_id": request_id}
        )
        return DepartmentOut.model_validate(department)

    except DepartmentNotFoundError as e:
        logger.error(f"Department not found: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving department {department_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def list_departments(
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_DEPARTMENT]))
) -> List[DepartmentOut]:
    """Retrieve a list of active departments with pagination."""
    try:
        if skip < 0 or (limit is not None and limit < 0):
            raise ValidationError(detail="Invalid pagination parameters")

        limit = limit or settings.DEFAULT_PAGE_SIZE
        cache_key = f"departments:{skip}:{limit}"
        cached_departments = await get_cache(cache_key)
        if cached_departments:
            return [DepartmentOut(**dept) for dept in cached_departments]

        query = select(Departments).where(
            Departments.is_active == True,
            Departments.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        departments = result.scalars().all()

        departments_dict = [DepartmentOut.model_validate(dept).model_dump() for dept in departments]
        await set_cache(cache_key, departments_dict, ttl=300)

        logger.info(
            f"Retrieved {len(departments)} departments",
            extra={"request_id": request_id}
        )
        return [DepartmentOut.model_validate(dept) for dept in departments]

    except ValidationError as e:
        logger.error(f"Validation error retrieving departments: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving departments: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def update_department(
    department_id: int,
    department_update: DepartmentUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.UPDATE_DEPARTMENT]))
) -> DepartmentOut:
    """Update a department with validation, logging, and cache clearing."""
    try:
        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        db_department = result.scalar_one_or_none()

        if not db_department:
            raise DepartmentNotFoundError(dept_id=department_id)

        update_data = department_update.model_dump(exclude_none=True)
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        # Validate department name uniqueness
        if "department_name" in update_data:
            query = select(Departments).where(
                Departments.department_name == update_data["department_name"],
                Departments.department_id != department_id,
                Departments.is_active == True,
                Departments.deleted_at == None
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise ValidationError(detail="Department name already exists")

        # Validate manager_id if updated
        if "manager_id" in update_data and update_data["manager_id"]:
            await validate_user_exists(db, update_data["manager_id"], request_id)

        old_values = db_department.__dict__.copy()
        for key, value in update_data.items():
            setattr(db_department, key, value)

        db_department.updated_at = datetime.now(timezone.utc)
        db.add(db_department)
        await db.commit()
        await db.refresh(db_department)

        # Invalidate cache
        await invalidate_cache_prefix("department")
        logger.debug(f"Cache cleared for department")

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_DEPARTMENT,
            table_affected="departments",
            record_id=db_department.department_id,
            old_values=old_values,
            new_values=db_department.__dict__,
            ip_address=str(request.client.host),
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc),
            request_id=request_id
        )
        db.add(system_log)
        await db.commit()

        logger.info(
            f"Department updated, department_id: {department_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return DepartmentOut.model_validate(db_department)

    except (DepartmentNotFoundError, ValidationError, UserNotFoundError) as e:
        logger.error(f"Error updating department {department_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating department {department_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def delete_department(
    department_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.DELETE_DEPARTMENT]))
) -> None:
    """Soft delete a department with validation, logging, and cache clearing."""
    try:
        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        db_department = result.scalar_one_or_none()

        if not db_department:
            raise DepartmentNotFoundError(dept_id=department_id)

        # Validate no users are assigned to the department
        await validate_department_not_assigned(department_id, db, request_id)

        db_department.is_active = False
        db_department.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        # Invalidate cache
        await invalidate_cache_prefix("department")
        logger.debug(f"Cache cleared for department")

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_DEPARTMENT,
            table_affected="departments",
            record_id=db_department.department_id,
            old_values=db_department.__dict__,
            new_values=None,
            ip_address=str(request.client.host),
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc),
            request_id=request_id
        )
        db.add(system_log)
        await db.commit()

        logger.info(
            f"Department soft deleted, department_id: {department_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except (DepartmentNotFoundError, BusinessLogicError) as e:
        logger.error(f"Error deleting department {department_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting department {department_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")