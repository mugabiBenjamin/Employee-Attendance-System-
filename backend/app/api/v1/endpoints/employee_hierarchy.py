from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime, timezone
from app.core.database import get_db
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.core.permissions import check_permissions
from app.core.security import get_current_active_user
from app.core.config import settings
from app.core.enums import Permission
from app.schemas.employee_hierarchy import EmployeeHierarchyCreate, EmployeeHierarchyUpdate, EmployeeHierarchyOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employee-hierarchy", tags=["Employee Hierarchy"])

async def is_admin_or_hr(db: AsyncSession, user: Users) -> bool:
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

@router.post("/", response_model=EmployeeHierarchyOut, status_code=status.HTTP_201_CREATED, summary="Create employee hierarchy")
async def create_employee_hierarchy(
    hierarchy: EmployeeHierarchyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> EmployeeHierarchyOut:
    try:
        has_permission = await check_permissions([Permission.MANAGE_EMPLOYEE_HIERARCHY.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create employee hierarchy")

        query = select(Users).where(Users.user_id == hierarchy.employee_id, Users.is_active == True, Users.deleted_at == None)
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

        query = select(Users).where(Users.user_id == hierarchy.manager_id, Users.is_active == True, Users.deleted_at == None)
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manager not found")

        if hierarchy.employee_id == hierarchy.manager_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee cannot be their own manager")

        query = select(EmployeeHierarchy).where(EmployeeHierarchy.employee_id == hierarchy.employee_id, EmployeeHierarchy.is_active == True)
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

        logger.info(f"Employee hierarchy created, hierarchy_id: {db_hierarchy.hierarchy_id}, employee_id: {db_hierarchy.employee_id}")
        return EmployeeHierarchyOut.model_validate(db_hierarchy)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating employee hierarchy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating employee hierarchy")

@router.get("/{hierarchy_id}", response_model=EmployeeHierarchyOut, summary="Get employee hierarchy by ID")
async def read_employee_hierarchy(
    hierarchy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> EmployeeHierarchyOut:
    try:
        has_permission = await check_permissions([Permission.VIEW_EMPLOYEE_HIERARCHY.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view employee hierarchy")

        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.hierarchy_id == hierarchy_id,
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
        result = await db.execute(query)
        hierarchy = result.scalar_one_or_none()

        if not hierarchy:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee hierarchy not found")

        logger.info(f"Retrieved employee hierarchy, hierarchy_id: {hierarchy_id}")
        return EmployeeHierarchyOut.model_validate(hierarchy)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving employee hierarchy {hierarchy_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving employee hierarchy")

@router.get("/", response_model=List[EmployeeHierarchyOut], summary="List all employee hierarchies")
async def read_employee_hierarchies(
    employee_id: Optional[int] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[EmployeeHierarchyOut]:
    try:
        has_permission = await check_permissions([Permission.VIEW_EMPLOYEE_HIERARCHY.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view employee hierarchies")

        query = select(EmployeeHierarchy).where(EmployeeHierarchy.is_active == True, EmployeeHierarchy.deleted_at == None)
        if employee_id:
            query = query.where(EmployeeHierarchy.employee_id == employee_id)
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        hierarchies = result.scalars().all()

        logger.info(f"Retrieved {len(hierarchies)} employee hierarchies")
        return [EmployeeHierarchyOut.model_validate(hierarchy) for hierarchy in hierarchies]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving employee hierarchies: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving employee hierarchies")

@router.put("/{hierarchy_id}", response_model=EmployeeHierarchyOut, summary="Update employee hierarchy")
async def update_employee_hierarchy(
    hierarchy_id: int,
    hierarchy_update: EmployeeHierarchyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> EmployeeHierarchyOut:
    try:
        has_permission = await check_permissions([Permission.MANAGE_EMPLOYEE_HIERARCHY.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update employee hierarchies")

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
        if "employee_id" in update_data:
            query = select(Users).where(Users.user_id == update_data["employee_id"], Users.is_active == True, Users.deleted_at == None)
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

        if "manager_id" in update_data:
            query = select(Users).where(Users.user_id == update_data["manager_id"], Users.is_active == True, Users.deleted_at == None)
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manager not found")

        if update_data.get("employee_id") or update_data.get("manager_id"):
            new_employee_id = update_data.get("employee_id", hierarchy.employee_id)
            if new_employee_id == update_data.get("manager_id", hierarchy.manager_id):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee cannot be their own manager")

            query = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == new_employee_id,
                EmployeeHierarchy.is_active == True,
                EmployeeHierarchy.hierarchy_id != hierarchy_id
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee already has a manager")

        for key, value in update_data.items():
            setattr(hierarchy, key, value)

        hierarchy.updated_at = datetime.now(timezone.utc)
        db.add(hierarchy)
        await db.commit()
        await db.refresh(hierarchy)

        logger.info(f"Employee hierarchy updated, hierarchy_id: {hierarchy_id}")
        return EmployeeHierarchyOut.model_validate(hierarchy)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating employee hierarchy {hierarchy_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating employee hierarchy")

@router.delete("/{hierarchy_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete employee hierarchy")
async def delete_employee_hierarchy(
    hierarchy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    try:
        has_permission = await check_permissions([Permission.MANAGE_EMPLOYEE_HIERARCHY.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete employee hierarchies")

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

        logger.info(f"Employee hierarchy soft deleted, hierarchy_id: {hierarchy_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting employee hierarchy {hierarchy_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting employee hierarchy")