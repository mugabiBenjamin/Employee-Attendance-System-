from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.users import Users
from app.schemas.employee_hierarchy import EmployeeHierarchyCreate, EmployeeHierarchyUpdate, EmployeeHierarchyOut
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import UserNotFoundError, EmployeeHierarchyError, ValidationError, DepartmentNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions, invalidate_user_cache
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_user_exists
from app.services.system_log_service import create_system_log
from app.schemas.system_log import SystemLogCreate
import logging

logger = logging.getLogger(__name__)

async def check_cyclic_hierarchy(db: AsyncSession, employee_id: int, supervisor_id: int, request_id: Optional[str] = None) -> None:
    """Check for cyclic hierarchy to prevent circular reporting structures."""
    try:
        if employee_id <= 0 or supervisor_id <= 0:
            raise ValidationError(detail="Invalid employee or manager ID")
        if employee_id == supervisor_id:
            raise EmployeeHierarchyError(detail="Employee cannot be their own manager")
        
        seen = {employee_id}
        current_id = supervisor_id
        while current_id:
            query = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == current_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result = await db.execute(query)
            hierarchy = result.scalar_one_or_none()
            if not hierarchy:
                break
            if hierarchy.supervisor_id in seen:
                raise EmployeeHierarchyError(detail="Cyclic hierarchy detected")
            seen.add(current_id)
            current_id = hierarchy.supervisor_id
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except EmployeeHierarchyError as e:
        logger.error(f"Cyclic hierarchy error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error checking cyclic hierarchy: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error checking cyclic hierarchy")

async def create_employee_hierarchy(
    hierarchy: EmployeeHierarchyCreate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.CREATE_HIERARCHY]))
) -> EmployeeHierarchyOut:
    """Create a new employee-manager relationship with validation, logging, and cache clearing."""
    try:
        # Validate employee and manager
        if hierarchy.employee_id <= 0 or hierarchy.supervisor_id <= 0:
            raise ValidationError(detail="Invalid employee or manager ID")
        await validate_user_exists(db, hierarchy.employee_id, request_id)
        await validate_user_exists(db, hierarchy.supervisor_id, request_id)
        if hierarchy.employee_id == hierarchy.supervisor_id:
            raise EmployeeHierarchyError(detail="Employee cannot be their own manager")

        # Check for existing active hierarchy
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.employee_id == hierarchy.employee_id,
            EmployeeHierarchy.is_active.is_(True),
            EmployeeHierarchy.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise EmployeeHierarchyError(detail="Employee already has an active manager assigned")

        # Check for cyclic hierarchy
        await check_cyclic_hierarchy(db, hierarchy.employee_id, hierarchy.supervisor_id, request_id)

        db_hierarchy = EmployeeHierarchy(
            **hierarchy.model_dump(),
            effective_from=datetime.now(timezone.utc).date(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_hierarchy)
        await db.commit()
        await db.refresh(db_hierarchy)

        # Invalidate caches
        await invalidate_cache_prefix("employee_hierarchy")
        await invalidate_cache_prefix(f"user:{hierarchy.employee_id}")
        await invalidate_cache_prefix(f"user:{hierarchy.supervisor_id}")
        invalidate_user_cache(hierarchy.employee_id)
        invalidate_user_cache(hierarchy.supervisor_id)
        logger.info(
            f"Cache invalidated for employee_hierarchy, employee_id:{hierarchy.employee_id}, supervisor_id:{hierarchy.supervisor_id}",
            extra={"request_id": request_id}
        )

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_HIERARCHY,
            table_affected="employee_hierarchy",
            record_id=db_hierarchy.hierarchy_id,
            old_values=None,
            new_values=db_hierarchy.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Employee hierarchy created, hierarchy_id: {db_hierarchy.hierarchy_id}, employee_id: {hierarchy.employee_id}, supervisor_id: {hierarchy.supervisor_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return EmployeeHierarchyOut.model_validate(db_hierarchy)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (UserNotFoundError, EmployeeHierarchyError) as e:
        logger.error(f"Error creating employee hierarchy: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY if isinstance(e, EmployeeHierarchyError) else status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating employee hierarchy: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating employee hierarchy")

async def get_employee_hierarchy(
    hierarchy_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_HIERARCHY, Permission.VIEW_OWN_HIERARCHY]))
) -> EmployeeHierarchyOut:
    """Retrieve an employee-manager relationship by ID."""
    try:
        if hierarchy_id <= 0:
            raise ValidationError(detail="Invalid hierarchy ID")

        cache_key = f"employee_hierarchy:{hierarchy_id}"
        cached_hierarchy = await get_cache(cache_key)
        if cached_hierarchy:
            logger.info(f"Cache hit for hierarchy_id: {hierarchy_id}", extra={"request_id": request_id})
            return EmployeeHierarchyOut(**cached_hierarchy)

        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.hierarchy_id == hierarchy_id,
            EmployeeHierarchy.is_active.is_(True),
            EmployeeHierarchy.deleted_at.is_(None)
        )
        result = await db.execute(query)
        hierarchy = result.scalar_one_or_none()

        if not hierarchy:
            raise EmployeeHierarchyError(detail=f"Employee hierarchy with ID {hierarchy_id} not found")

        if not any(p == Permission.VIEW_HIERARCHY or p == Permission.MANAGE_EMPLOYEES for p in current_user.permissions) and hierarchy.employee_id != current_user.user_id and hierarchy.supervisor_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this hierarchy"
            )

        hierarchy_dict = EmployeeHierarchyOut.model_validate(hierarchy).model_dump()
        await set_cache(cache_key, hierarchy_dict, ttl=300)
        logger.info(f"Cache set for hierarchy_id: {hierarchy_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved employee hierarchy, hierarchy_id: {hierarchy_id}, employee_id: {hierarchy.employee_id}, supervisor_id: {hierarchy.supervisor_id}",
            extra={"request_id": request_id}
        )
        return EmployeeHierarchyOut.model_validate(hierarchy)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except EmployeeHierarchyError as e:
        logger.error(f"Hierarchy not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving employee hierarchy {hierarchy_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving employee hierarchy")

async def list_employee_hierarchies(
    employee_id: Optional[int] = None,
    department_id: Optional[int] = None,
    supervisor_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_HIERARCHY, Permission.VIEW_OWN_HIERARCHY]))
) -> List[EmployeeHierarchyOut]:
    """Retrieve a list of active employee-manager relationships with pagination."""
    try:
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")

        target_employee_id = employee_id
        if not any(p == Permission.VIEW_HIERARCHY or p == Permission.MANAGE_EMPLOYEES for p in current_user.permissions):
            target_employee_id = current_user.user_id

        if target_employee_id:
            if target_employee_id <= 0:
                raise ValidationError(detail="Invalid employee ID")
            await validate_user_exists(db, target_employee_id, request_id)
        if supervisor_id:
            if supervisor_id <= 0:
                raise ValidationError(detail="Invalid manager ID")
            await validate_user_exists(db, supervisor_id, request_id)

        cache_key = f"employee_hierarchies:{target_employee_id or 'all'}:{department_id or 'all'}:{supervisor_id or 'all'}:{skip}:{limit or settings.DEFAULT_PAGE_SIZE}"
        cached_hierarchies = await get_cache(cache_key)
        if cached_hierarchies:
            logger.info(f"Cache hit for employee_hierarchies, employee_id: {target_employee_id or 'all'}, department_id: {department_id or 'all'}, supervisor_id: {supervisor_id or 'all'}", extra={"request_id": request_id})
            return [EmployeeHierarchyOut(**h) for h in cached_hierarchies]

        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.is_active.is_(True),
            EmployeeHierarchy.deleted_at.is_(None)
        )
        if target_employee_id:
            query = query.where(
                (EmployeeHierarchy.employee_id == target_employee_id) |
                (EmployeeHierarchy.supervisor_id == target_employee_id)
            )
        if department_id:
            if department_id <= 0:
                raise ValidationError(detail="Invalid department ID")
            from app.models.user_departments import UserDepartments
            from app.core.validators import validate_department_exists
            await validate_department_exists(db, department_id, request_id)
            query = query.join(UserDepartments, UserDepartments.user_id == EmployeeHierarchy.employee_id).where(
                UserDepartments.department_id == department_id,
                UserDepartments.is_active.is_(True),
                UserDepartments.deleted_at.is_(None)
            )
        if supervisor_id:
            query = query.where(EmployeeHierarchy.supervisor_id == supervisor_id)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        hierarchies = result.scalars().all()

        hierarchies_dict = [EmployeeHierarchyOut.model_validate(h).model_dump() for h in hierarchies]
        await set_cache(cache_key, hierarchies_dict, ttl=300)
        logger.info(f"Cache set for employee_hierarchies, employee_id: {target_employee_id or 'all'}, department_id: {department_id or 'all'}, supervisor_id: {supervisor_id or 'all'}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(hierarchies)} employee hierarchies for employee_id: {target_employee_id or 'all'}, department_id: {department_id or 'all'}, supervisor_id: {supervisor_id or 'all'}",
            extra={"request_id": request_id}
        )
        return [EmployeeHierarchyOut.model_validate(hierarchy) for hierarchy in hierarchies]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (UserNotFoundError, DepartmentNotFoundError) as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving employee hierarchies: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving employee hierarchies")

async def update_employee_hierarchy(
    hierarchy_id: int,
    hierarchy_update: EmployeeHierarchyUpdate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.UPDATE_HIERARCHY]))
) -> EmployeeHierarchyOut:
    """Update an employee-manager relationship with validation, logging, and cache clearing."""
    try:
        if hierarchy_id <= 0:
            raise ValidationError(detail="Invalid hierarchy ID")

        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.hierarchy_id == hierarchy_id,
            EmployeeHierarchy.is_active.is_(True),
            EmployeeHierarchy.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_hierarchy = result.scalar_one_or_none()

        if not db_hierarchy:
            raise EmployeeHierarchyError(detail=f"Employee hierarchy with ID {hierarchy_id} not found")

        update_data = hierarchy_update.model_dump(exclude_none=True)
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        old_employee_id = db_hierarchy.employee_id
        old_supervisor_id = db_hierarchy.supervisor_id
        if "supervisor_id" in update_data:
            if update_data["supervisor_id"] <= 0:
                raise ValidationError(detail="Invalid manager ID")
            await validate_user_exists(db, update_data["supervisor_id"], request_id)
            if update_data["supervisor_id"] == db_hierarchy.employee_id:
                raise EmployeeHierarchyError(detail="Employee cannot be their own manager")
            await check_cyclic_hierarchy(db, db_hierarchy.employee_id, update_data["supervisor_id"], request_id)

        old_values = db_hierarchy.__dict__.copy()
        for key, value in update_data.items():
            setattr(db_hierarchy, key, value)

        db_hierarchy.updated_at = datetime.now(timezone.utc)
        db.add(db_hierarchy)
        await db.commit()
        await db.refresh(db_hierarchy)

        # Invalidate caches
        await invalidate_cache_prefix("employee_hierarchy")
        await invalidate_cache_prefix(f"user:{db_hierarchy.employee_id}")
        await invalidate_cache_prefix(f"user:{db_hierarchy.supervisor_id}")
        invalidate_user_cache(db_hierarchy.employee_id)
        invalidate_user_cache(db_hierarchy.supervisor_id)
        if old_employee_id != db_hierarchy.employee_id:
            invalidate_user_cache(old_employee_id)
        if old_supervisor_id != db_hierarchy.supervisor_id:
            invalidate_user_cache(old_supervisor_id)
        logger.info(
            f"Cache invalidated for employee_hierarchy, employee_id:{db_hierarchy.employee_id},{old_employee_id}, supervisor_id:{db_hierarchy.supervisor_id},{old_supervisor_id}",
            extra={"request_id": request_id}
        )

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_HIERARCHY,
            table_affected="employee_hierarchy",
            record_id=hierarchy_id,
            old_values=old_values,
            new_values=db_hierarchy.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Employee hierarchy updated, hierarchy_id: {hierarchy_id}, employee_id: {db_hierarchy.employee_id}, supervisor_id: {db_hierarchy.supervisor_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return EmployeeHierarchyOut.model_validate(db_hierarchy)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (EmployeeHierarchyError, UserNotFoundError) as e:
        logger.error(f"Error updating employee hierarchy: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY if isinstance(e, EmployeeHierarchyError) else status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error updating employee hierarchy {hierarchy_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating employee hierarchy")

async def delete_employee_hierarchy(
    hierarchy_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.DELETE_HIERARCHY]))
) -> None:
    """Soft delete an employee-manager relationship with validation, logging, and cache clearing."""
    try:
        if hierarchy_id <= 0:
            raise ValidationError(detail="Invalid hierarchy ID")

        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.hierarchy_id == hierarchy_id,
            EmployeeHierarchy.is_active.is_(True),
            EmployeeHierarchy.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_hierarchy = result.scalar_one_or_none()

        if not db_hierarchy:
            raise EmployeeHierarchyError(detail=f"Employee hierarchy with ID {hierarchy_id} not found")

        # Check if the employee is a manager of others
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.supervisor_id == db_hierarchy.employee_id,
            EmployeeHierarchy.is_active.is_(True),
            EmployeeHierarchy.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if result.scalars().all():
            raise EmployeeHierarchyError(detail="Cannot delete hierarchy; employee is a manager of others")

        db_hierarchy.is_active = False
        db_hierarchy.deleted_at = datetime.now(timezone.utc)
        db_hierarchy.updated_at = datetime.now(timezone.utc)
        db.add(db_hierarchy)
        await db.commit()

        # Invalidate caches
        await invalidate_cache_prefix("employee_hierarchy")
        await invalidate_cache_prefix(f"user:{db_hierarchy.employee_id}")
        await invalidate_cache_prefix(f"user:{db_hierarchy.supervisor_id}")
        invalidate_user_cache(db_hierarchy.employee_id)
        invalidate_user_cache(db_hierarchy.supervisor_id)
        logger.info(
            f"Cache invalidated for employee_hierarchy, employee_id:{db_hierarchy.employee_id}, supervisor_id:{db_hierarchy.supervisor_id}",
            extra={"request_id": request_id}
        )

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_HIERARCHY,
            table_affected="employee_hierarchy",
            record_id=hierarchy_id,
            old_values=db_hierarchy.__dict__,
            new_values=None,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Employee hierarchy soft deleted, hierarchy_id: {hierarchy_id}, employee_id: {db_hierarchy.employee_id}, supervisor_id: {db_hierarchy.supervisor_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except EmployeeHierarchyError as e:
        logger.error(f"Hierarchy error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY if "Cannot delete" in str(e) else status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error deleting employee hierarchy {hierarchy_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting employee hierarchy")