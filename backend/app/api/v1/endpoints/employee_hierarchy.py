from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime, timezone
from app.core.database import get_db
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.config import settings
from app.core.enums import Permission
from app.schemas.employee_hierarchy import (
    EmployeeHierarchyCreate, 
    EmployeeHierarchyUpdate, 
    EmployeeHierarchyOut
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employee-hierarchy", tags=["Employee Hierarchy"])

@router.post("/", response_model=EmployeeHierarchyOut, status_code=status.HTTP_201_CREATED)
@require_permissions([Permission.MANAGE_EMPLOYEES])
async def create_employee_hierarchy(
    hierarchy: EmployeeHierarchyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> EmployeeHierarchyOut:
    """Create employee hierarchy relationship. Requires MANAGE_EMPLOYEES permission."""
    try:
        # Validate employee exists
        query = select(Users).where(
            Users.user_id == hierarchy.employee_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

        # Validate manager exists
        query = select(Users).where(
            Users.user_id == hierarchy.manager_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manager not found")

        # Prevent self-management
        if hierarchy.employee_id == hierarchy.manager_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee cannot be their own manager")

        # Check if employee already has a manager
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.employee_id == hierarchy.employee_id,
            EmployeeHierarchy.is_active == True
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee already has a manager")

        db_hierarchy = EmployeeHierarchy(
            **hierarchy.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_hierarchy)
        await db.commit()
        await db.refresh(db_hierarchy)

        logger.info(f"Hierarchy created: {db_hierarchy.hierarchy_id} (employee: {db_hierarchy.employee_id})")
        return EmployeeHierarchyOut.model_validate(db_hierarchy)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating employee hierarchy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating employee hierarchy")

@router.get("/{hierarchy_id}", response_model=EmployeeHierarchyOut)
@require_permissions([Permission.VIEW_ALL_ATTENDANCE, Permission.VIEW_TEAM_ATTENDANCE, Permission.VIEW_OWN_ATTENDANCE])
async def get_employee_hierarchy(
    hierarchy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> EmployeeHierarchyOut:
    """Get hierarchy by ID. Requires VIEW_ALL_ATTENDANCE for all, VIEW_TEAM_ATTENDANCE for team, or VIEW_OWN_ATTENDANCE for own hierarchy."""
    try:
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.hierarchy_id == hierarchy_id,
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
        result = await db.execute(query)
        hierarchy = result.scalar_one_or_none()

        if not hierarchy:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee hierarchy not found")

        # Check if user is viewing their own hierarchy, their team's, or has VIEW_ALL_ATTENDANCE
        if hierarchy.employee_id != current_user.user_id and hierarchy.manager_id != current_user.user_id:
            await require_permissions([Permission.VIEW_ALL_ATTENDANCE])(get_employee_hierarchy)(hierarchy_id=hierarchy_id, db=db, current_user=current_user)

        return EmployeeHierarchyOut.model_validate(hierarchy)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving employee hierarchy {hierarchy_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving employee hierarchy")

@router.get("/", response_model=List[EmployeeHierarchyOut])
@require_permissions([Permission.VIEW_ALL_ATTENDANCE, Permission.VIEW_TEAM_ATTENDANCE, Permission.VIEW_OWN_ATTENDANCE])
async def list_employee_hierarchies(
    employee_id: Optional[int] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[EmployeeHierarchyOut]:
    """List hierarchies. Requires VIEW_ALL_ATTENDANCE for all, VIEW_TEAM_ATTENDANCE for team, or VIEW_OWN_ATTENDANCE for own hierarchy."""
    try:
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
        
        if employee_id:
            # Only allow viewing specific employee if authorized
            if employee_id != current_user.user_id:
                await require_permissions([Permission.VIEW_ALL_ATTENDANCE])(list_employee_hierarchies)(employee_id=employee_id, skip=skip, limit=limit, db=db, current_user=current_user)
            query = query.where(EmployeeHierarchy.employee_id == employee_id)
        else:
            # Restrict to team or own hierarchy if not VIEW_ALL_ATTENDANCE
            if not (await require_permissions([Permission.VIEW_ALL_ATTENDANCE])(list_employee_hierarchies)(employee_id=employee_id, skip=skip, limit=limit, db=db, current_user=current_user)):
                query = query.where(
                    (EmployeeHierarchy.manager_id == current_user.user_id) |
                    (EmployeeHierarchy.employee_id == current_user.user_id)
                )
        
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        hierarchies = result.scalars().all()

        return [EmployeeHierarchyOut.model_validate(hierarchy) for hierarchy in hierarchies]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving employee hierarchies: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving employee hierarchies")

@router.put("/{hierarchy_id}", response_model=EmployeeHierarchyOut)
@require_permissions([Permission.MANAGE_EMPLOYEES])
async def update_employee_hierarchy(
    hierarchy_id: int,
    hierarchy_update: EmployeeHierarchyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> EmployeeHierarchyOut:
    """Update employee hierarchy. Requires MANAGE_EMPLOYEES permission."""
    try:
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.hierarchy_id == hierarchy_id,
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
        result = await db.execute(query)
        hierarchy = result.scalar_one_or_none()

        if not hierarchy:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee hierarchy not found")

        update_data = hierarchy_update.model_dump(exclude_none=True)
        
        # Validate employee if being updated
        if "employee_id" in update_data:
            query = select(Users).where(
                Users.user_id == update_data["employee_id"],
                Users.is_active == True,
                Users.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

        # Validate manager if being updated
        if "manager_id" in update_data:
            query = select(Users).where(
                Users.user_id == update_data["manager_id"],
                Users.is_active == True,
                Users.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manager not found")

        # Validate no self-management and no duplicate hierarchy
        if update_data.get("employee_id") or update_data.get("manager_id"):
            new_employee_id = update_data.get("employee_id", hierarchy.employee_id)
            new_manager_id = update_data.get("manager_id", hierarchy.manager_id)
            
            if new_employee_id == new_manager_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee cannot be their own manager")

            # Check for duplicate hierarchy
            query = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == new_employee_id,
                EmployeeHierarchy.is_active == True,
                EmployeeHierarchy.hierarchy_id != hierarchy_id
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee already has a manager")

        # Apply updates
        for key, value in update_data.items():
            setattr(hierarchy, key, value)

        hierarchy.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(hierarchy)

        logger.info(f"Hierarchy updated: {hierarchy_id}")
        return EmployeeHierarchyOut.model_validate(hierarchy)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating employee hierarchy {hierarchy_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating employee hierarchy")

@router.delete("/{hierarchy_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions([Permission.MANAGE_EMPLOYEES])
async def delete_employee_hierarchy(
    hierarchy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    """Soft delete employee hierarchy. Requires MANAGE_EMPLOYEES permission."""
    try:
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.hierarchy_id == hierarchy_id,
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
        result = await db.execute(query)
        hierarchy = result.scalar_one_or_none()

        if not hierarchy:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee hierarchy not found")

        hierarchy.is_active = False
        hierarchy.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Hierarchy deleted: {hierarchy_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting employee hierarchy {hierarchy_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting employee hierarchy")