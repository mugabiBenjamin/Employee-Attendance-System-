from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timezone
from app.core.database import get_db
from app.models.departments import Departments
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.models.users import Users
from app.core.config import settings
from app.core.permissions import check_permissions
from app.core.security import get_current_active_user
from app.core.enums import Permission
from app.schemas.department import DepartmentCreate, DepartmentUpdate, DepartmentOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/departments", tags=["Departments"])

async def is_admin_or_manager(db: AsyncSession, user: Users) -> bool:
    try:
        query = select(UserRoles).join(Roles).where(
            UserRoles.user_id == user.user_id,
            UserRoles.is_active == True,
            Roles.role_name.in_(["Manager", "HR", "Admin", "Super_Admin"]),
            Roles.is_active == True
        )
        result = await db.execute(query)
        return result.scalar_one_or_none() is not None
    except Exception as e:
        logger.error(f"Error checking admin/manager role for user_id {user.user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error checking user role")

@router.post("/", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED, summary="Create new department", description="Create a new department. Requires manage_departments permission.")
async def create_new_department(
    department: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> DepartmentOut:
    try:
        has_permission = await check_permissions([Permission.MANAGE_DEPARTMENTS.value], current_user, db)
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create departments")

        query = select(Departments).where(Departments.department_name == department.department_name, Departments.is_active == True)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department name already exists")

        db_department = Departments(
            **department.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating department")

@router.get("/{department_id}", response_model=DepartmentOut, summary="Get department by ID", description="Retrieve department details. Requires view_departments permission or manager/admin access.")
async def read_department(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> DepartmentOut:
    try:
        has_permission = await check_permissions([Permission.VIEW_DEPARTMENTS.value], current_user, db)
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view departments")

        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        department = result.scalar_one_or_none()

        if not department:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

        logger.info(f"Retrieved department, department_id: {department_id}")
        return DepartmentOut.model_validate(department)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving department {department_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving department")

@router.get("/", response_model=List[DepartmentOut], summary="List all departments", description="Retrieve all departments with pagination. Requires view_departments permission or manager/admin access.")
async def read_departments(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[DepartmentOut]:
    try:
        has_permission = await check_permissions([Permission.VIEW_DEPARTMENTS.value], current_user, db)
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view departments")

        query = select(Departments).where(
            Departments.is_active == True,
            Departments.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        departments = result.scalars().all()

        logger.info(f"Retrieved {len(departments)} departments")
        return [DepartmentOut.model_validate(dept) for dept in departments]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving departments: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving departments")

@router.put("/{department_id}", response_model=DepartmentOut, summary="Update department", description="Update department information. Requires manage_departments permission.")
async def update_existing_department(
    department_id: int,
    department_update: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> DepartmentOut:
    try:
        has_permission = await check_permissions([Permission.MANAGE_DEPARTMENTS.value], current_user, db)
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update departments")

        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        department = result.scalar_one_or_none()

        if not department:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

        update_data = department_update.model_dump(exclude_none=True)
        if "department_name" in update_data and update_data["department_name"] != department.department_name:
            query = select(Departments).where(Departments.department_name == update_data["department_name"], Departments.is_active == True)
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department name already exists")

        for key, value in update_data.items():
            setattr(department, key, value)

        department.updated_at = datetime.now(timezone.utc)
        db.add(department)
        await db.commit()
        await db.refresh(department)

        logger.info(f"Department updated, department_id: {department_id}")
        return DepartmentOut.model_validate(department)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating department {department_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating department")

@router.delete("/{department_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete department", description="Soft delete a department. Requires manage_departments permission.")
async def delete_existing_department(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    try:
        has_permission = await check_permissions([Permission.MANAGE_DEPARTMENTS.value], current_user, db)
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete departments")

        query = select(Departments).where(
            Departments.department_id == department_id,
            Departments.is_active == True,
            Departments.deleted_at == None
        )
        result = await db.execute(query)
        department = result.scalar_one_or_none()

        if not department:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

        department.is_active = False
        department.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Department soft deleted, department_id: {department_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting department {department_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting department")