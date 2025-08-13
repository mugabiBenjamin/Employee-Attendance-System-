from typing import List, Optional
from fastapi import HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.user_departments import UserDepartments
from app.models.users import Users
from app.models.departments import Departments
from app.schemas.user_department import UserDepartmentCreate, UserDepartmentUpdate, UserDepartmentOut
from app.core.config import settings
from app.core.enums import SystemAction, Permission
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.services.system_log_service import SystemLogService, get_system_log_service
from app.schemas.system_log import SystemLogCreate
import logging

logger = logging.getLogger(__name__)

async def create_user_department(
    db: AsyncSession,
    user_department: UserDepartmentCreate,
    current_user: Users = Depends(get_current_user),
    _: str = Depends(require_permissions([Permission.CREATE_USER_DEPARTMENT])),
    log_service: SystemLogService = Depends(get_system_log_service)
) -> UserDepartmentOut:
    """Assign a user to a department. Requires CREATE_USER_DEPARTMENT permission."""
    try:
        # Validate user and department exist
        await _validate_user_exists(db, user_department.user_id)
        await _validate_department_exists(db, user_department.department_id)
        
        # Check for existing assignment
        if await _assignment_exists(db, user_department.user_id, user_department.department_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already assigned to this department"
            )

        # Handle primary assignment logic
        if user_department.is_primary:
            await _clear_existing_primary(db, user_department.user_id)

        # Create assignment
        db_user_department = UserDepartments(
            user_id=user_department.user_id,
            department_id=user_department.department_id,
            is_primary=user_department.is_primary,
            assigned_at=datetime.now(timezone.utc)
        )
        
        db.add(db_user_department)
        await db.commit()
        await db.refresh(db_user_department)

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="user_departments",
            record_id=db_user_department.user_department_id,
            old_values=None,
            new_values=db_user_department.__dict__
        )
        await log_service.create_system_log(log, current_user)

        logger.info(f"User department assignment created: {db_user_department.user_department_id}")
        return UserDepartmentOut.model_validate(db_user_department)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user department assignment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user department assignment"
        )

async def get_user_department_by_id(
    db: AsyncSession,
    user_department_id: int,
    _: str = Depends(require_permissions([Permission.VIEW_USER_DEPARTMENT]))
) -> Optional[UserDepartmentOut]:
    """Retrieve a user-department assignment by ID. Requires VIEW_USER_DEPARTMENT permission."""
    try:
        query = select(UserDepartments).where(
            UserDepartments.user_department_id == user_department_id,
            UserDepartments.is_active == True,
            UserDepartments.deleted_at == None
        )
        result = await db.execute(query)
        user_department = result.scalar_one_or_none()
        
        if not user_department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User department assignment not found"
            )

        return UserDepartmentOut.model_validate(user_department)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user department assignment {user_department_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user department assignment"
        )

async def get_user_departments(
    db: AsyncSession,
    user_id: int,
    skip: int = 0,
    limit: int = None,
    _: str = Depends(require_permissions([Permission.VIEW_USER_DEPARTMENT]))
) -> List[UserDepartmentOut]:
    """Get department assignments for a user. Requires VIEW_USER_DEPARTMENT permission."""
    try:
        await _validate_user_exists(db, user_id)
        
        limit = limit or settings.DEFAULT_PAGE_SIZE
        
        query = (
            select(UserDepartments)
            .where(
                UserDepartments.user_id == user_id,
                UserDepartments.is_active == True,
                UserDepartments.deleted_at == None
            )
            .order_by(UserDepartments.is_primary.desc(), UserDepartments.assigned_at.desc())
            .offset(skip)
            .limit(limit)
        )
        
        result = await db.execute(query)
        user_departments = result.scalars().all()

        logger.info(f"Retrieved {len(user_departments)} department assignments for user {user_id}")
        return [UserDepartmentOut.model_validate(ud) for ud in user_departments]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving department assignments for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve department assignments"
        )

async def update_user_department(
    db: AsyncSession,
    user_department_id: int,
    update_data: UserDepartmentUpdate,
    current_user: Users = Depends(get_current_user),
    _: str = Depends(require_permissions([Permission.UPDATE_USER_DEPARTMENT])),
    log_service: SystemLogService = Depends(get_system_log_service)
) -> UserDepartmentOut:
    """Update a user-department assignment. Requires UPDATE_USER_DEPARTMENT permission."""
    try:
        # Get existing assignment
        query = select(UserDepartments).where(
            UserDepartments.user_department_id == user_department_id,
            UserDepartments.is_active == True,
            UserDepartments.deleted_at == None
        )
        result = await db.execute(query)
        db_user_department = result.scalar_one_or_none()

        if not db_user_department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User department assignment not found"
            )

        old_values = {k: v for k, v in db_user_department.__dict__.items() if not k.startswith('_')}
        changes = update_data.model_dump(exclude_none=True)

        # Validate changes
        if "user_id" in changes:
            await _validate_user_exists(db, changes["user_id"])
            
        if "department_id" in changes:
            await _validate_department_exists(db, changes["department_id"])
            # Check for duplicate assignment
            new_user_id = changes.get("user_id", db_user_department.user_id)
            if await _assignment_exists(db, new_user_id, changes["department_id"], exclude_id=user_department_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User is already assigned to this department"
                )

        # Handle primary assignment logic
        if changes.get("is_primary"):
            user_id = changes.get("user_id", db_user_department.user_id)
            await _clear_existing_primary(db, user_id, exclude_id=user_department_id)

        # Apply updates
        for key, value in changes.items():
            setattr(db_user_department, key, value)

        db_user_department.updated_at = datetime.now(timezone.utc)
        db.add(db_user_department)
        await db.commit()
        await db.refresh(db_user_department)

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE,
            table_affected="user_departments",
            record_id=user_department_id,
            old_values=old_values,
            new_values=db_user_department.__dict__
        )
        await log_service.create_system_log(log, current_user)

        logger.info(f"User department assignment updated: {user_department_id}")
        return UserDepartmentOut.model_validate(db_user_department)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user department assignment {user_department_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user department assignment"
        )

async def delete_user_department(
    db: AsyncSession,
    user_department_id: int,
    current_user: Users = Depends(get_current_user),
    _: str = Depends(require_permissions([Permission.DELETE_USER_DEPARTMENT])),
    log_service: SystemLogService = Depends(get_system_log_service)
) -> None:
    """Soft delete a user-department assignment. Requires DELETE_USER_DEPARTMENT permission."""
    try:
        query = select(UserDepartments).where(
            UserDepartments.user_department_id == user_department_id,
            UserDepartments.is_active == True,
            UserDepartments.deleted_at == None
        )
        result = await db.execute(query)
        db_user_department = result.scalar_one_or_none()

        if not db_user_department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User department assignment not found"
            )

        old_values = {k: v for k, v in db_user_department.__dict__.items() if not k.startswith('_')}
        
        db_user_department.is_active = False
        db_user_department.deleted_at = datetime.now(timezone.utc)
        db.add(db_user_department)
        await db.commit()

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE,
            table_affected="user_departments",
            record_id=user_department_id,
            old_values=old_values,
            new_values=None
        )
        await log_service.create_system_log(log, current_user)

        logger.info(f"User department assignment soft deleted: {user_department_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user department assignment {user_department_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user department assignment"
        )

# Helper functions
async def _validate_user_exists(db: AsyncSession, user_id: int) -> None:
    """Validate that user exists and is active."""
    query = select(Users).where(
        Users.user_id == user_id,
        Users.is_active == True,
        Users.deleted_at == None
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

async def _validate_department_exists(db: AsyncSession, department_id: int) -> None:
    """Validate that department exists and is active."""
    query = select(Departments).where(
        Departments.department_id == department_id,
        Departments.is_active == True,
        Departments.deleted_at == None
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found"
        )

async def _assignment_exists(db: AsyncSession, user_id: int, department_id: int, exclude_id: int = None) -> bool:
    """Check if user is already assigned to department."""
    query = select(UserDepartments).where(
        UserDepartments.user_id == user_id,
        UserDepartments.department_id == department_id,
        UserDepartments.is_active == True,
        UserDepartments.deleted_at == None
    )
    if exclude_id:
        query = query.where(UserDepartments.user_department_id != exclude_id)
    
    result = await db.execute(query)
    return result.scalar_one_or_none() is not None

async def _clear_existing_primary(db: AsyncSession, user_id: int, exclude_id: int = None) -> None:
    """Clear existing primary department assignments for user."""
    query = select(UserDepartments).where(
        UserDepartments.user_id == user_id,
        UserDepartments.is_primary == True,
        UserDepartments.is_active == True,
        UserDepartments.deleted_at == None
    )
    if exclude_id:
        query = query.where(UserDepartments.user_department_id != exclude_id)
    
    result = await db.execute(query)
    existing_primary = result.scalars().all()
    
    for assignment in existing_primary:
        assignment.is_primary = False
        db.add(assignment)
    await db.commit()