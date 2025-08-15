from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.schemas.employee_hierarchy import EmployeeHierarchyCreate, EmployeeHierarchyUpdate, EmployeeHierarchyOut
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import UserNotFoundError, EmployeeHierarchyError, ResourceNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

async def create_employee_hierarchy(
    hierarchy: EmployeeHierarchyCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.MANAGE_EMPLOYEES]))
) -> EmployeeHierarchyOut:
    """
    Create a new employee-manager relationship with validation and logging.
    """
    try:
        # Validate employee_id and manager_id
        query = select(Users).where(
            Users.user_id.in_([hierarchy.employee_id, hierarchy.manager_id]),
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        users = result.scalars().all()
        if len(users) != 2:
            raise UserNotFoundError(detail="Employee or manager not found")

        # Check for existing hierarchy
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.employee_id == hierarchy.employee_id,
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise EmployeeHierarchyError(detail="Employee already has a manager assigned")

        # Prevent self-reporting
        if hierarchy.employee_id == hierarchy.manager_id:
            raise EmployeeHierarchyError(detail="Employee cannot be their own manager")

        # Create hierarchy
        db_hierarchy = EmployeeHierarchy(
            **EmployeeHierarchyCreate(**hierarchy.model_dump()).model_dump(),
            effective_from=datetime.now(timezone.utc).date(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_hierarchy)
        await db.commit()
        await db.refresh(db_hierarchy)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="employee_hierarchy",
            record_id=db_hierarchy.hierarchy_id,
            old_values=None,
            new_values=db_hierarchy.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Employee hierarchy created, hierarchy_id: {db_hierarchy.hierarchy_id}, employee_id: {hierarchy.employee_id}")
        return EmployeeHierarchyOut.model_validate(db_hierarchy)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating employee hierarchy: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating employee hierarchy"
        )

async def get_employee_hierarchy_by_id(
    hierarchy_id: int,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.MANAGE_EMPLOYEES]))
) -> Optional[EmployeeHierarchyOut]:
    """
    Retrieve an employee-manager relationship by ID.
    """
    try:
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.hierarchy_id == hierarchy_id,
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
        result = await db.execute(query)
        hierarchy = result.scalar_one_or_none()

        if not hierarchy:
            raise ResourceNotFoundError(resource="Employee hierarchy", identifier=f"ID {hierarchy_id}")

        return EmployeeHierarchyOut.model_validate(hierarchy)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving employee hierarchy {hierarchy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving employee hierarchy"
        )

async def get_employee_hierarchies(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.MANAGE_EMPLOYEES]))
) -> List[EmployeeHierarchyOut]:
    """
    Retrieve a list of active employee-manager relationships with pagination.
    """
    try:
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        ).offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        result = await db.execute(query)
        hierarchies = result.scalars().all()

        logger.info(f"Retrieved {len(hierarchies)} employee hierarchies")
        return [EmployeeHierarchyOut.model_validate(hierarchy) for hierarchy in hierarchies]

    except Exception as e:
        logger.error(f"Error retrieving employee hierarchies: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving employee hierarchies"
        )

async def update_employee_hierarchy(
    hierarchy_id: int,
    hierarchy_update: EmployeeHierarchyUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.MANAGE_EMPLOYEES]))
) -> EmployeeHierarchyOut:
    """
    Update an employee-manager relationship with validation and logging.
    """
    try:
        # Retrieve hierarchy
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.hierarchy_id == hierarchy_id,
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
        result = await db.execute(query)
        db_hierarchy = result.scalar_one_or_none()

        if not db_hierarchy:
            raise ResourceNotFoundError(resource="Employee hierarchy", identifier=f"ID {hierarchy_id}")

        # Validate manager_id if updated
        update_data = hierarchy_update.model_dump(exclude_none=True)
        if "manager_id" in update_data:
            query = select(Users).where(
                Users.user_id == update_data["manager_id"],
                Users.is_active == True,
                Users.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise UserNotFoundError(user_id=update_data["manager_id"])

            # Prevent self-reporting
            if update_data["manager_id"] == db_hierarchy.employee_id:
                raise EmployeeHierarchyError(detail="Employee cannot be their own manager")

        # Store old values for logging
        old_values = db_hierarchy.__dict__.copy()

        # Apply updates
        for key, value in update_data.items():
            setattr(db_hierarchy, key, value)

        db_hierarchy.updated_at = datetime.now(timezone.utc)
        db.add(db_hierarchy)
        await db.commit()
        await db.refresh(db_hierarchy)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE,
            table_affected="employee_hierarchy",
            record_id=hierarchy_id,
            old_values=old_values,
            new_values=db_hierarchy.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Employee hierarchy updated, hierarchy_id: {hierarchy_id}")
        return EmployeeHierarchyOut.model_validate(db_hierarchy)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating employee hierarchy {hierarchy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating employee hierarchy"
        )

async def delete_employee_hierarchy(
    hierarchy_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.MANAGE_EMPLOYEES]))
) -> None:
    """
    Soft delete an employee-manager relationship with logging.
    """
    try:
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.hierarchy_id == hierarchy_id,
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
        result = await db.execute(query)
        db_hierarchy = result.scalar_one_or_none()

        if not db_hierarchy:
            raise ResourceNotFoundError(resource="Employee hierarchy", identifier=f"ID {hierarchy_id}")

        db_hierarchy.is_active = False
        db_hierarchy.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.DELETE,
            table_affected="employee_hierarchy",
            record_id=hierarchy_id,
            old_values=db_hierarchy.__dict__,
            new_values=None,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Employee hierarchy soft deleted, hierarchy_id: {hierarchy_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting employee hierarchy {hierarchy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting employee hierarchy"
        )