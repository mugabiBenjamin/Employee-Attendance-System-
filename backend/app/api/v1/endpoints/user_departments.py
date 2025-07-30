from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime, timezone
from app.core.database import get_db
from app.models.user_departments import UserDepartments
from app.models.users import Users
from app.models.departments import Departments
from app.core.permissions import check_permissions
from app.core.security import get_current_active_user
from app.core.config import settings
from app.core.enums import Permission
from app.schemas.user_department import UserDepartmentCreate, UserDepartmentUpdate, UserDepartmentOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-departments", tags=["User Departments"])

@router.post("/", response_model=UserDepartmentOut, status_code=status.HTTP_201_CREATED, summary="Create user department assignment")
async def create_user_department(
    user_department: UserDepartmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserDepartmentOut:
    """Create a user department assignment. Requires MANAGE_DEPARTMENTS permission."""
    try:
        await check_permissions([Permission.MANAGE_DEPARTMENTS.value], current_user, db)

        # Verify user exists
        query = select(Users).where(Users.user_id == user_department.user_id, Users.is_active == True, Users.deleted_at == None)
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Verify department exists
        query = select(Departments).where(Departments.department_id == user_department.department_id, Departments.is_active == True, Departments.deleted_at == None)
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

        # Check for existing assignment
        query = select(UserDepartments).where(
            UserDepartments.user_id == user_department.user_id,
            UserDepartments.department_id == user_department.department_id,
            UserDepartments.is_active == True
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User department assignment already exists")

        # Handle primary department logic
        if user_department.is_primary:
            # Set existing primary departments to non-primary
            query = select(UserDepartments).where(
                UserDepartments.user_id == user_department.user_id,
                UserDepartments.is_primary == True,
                UserDepartments.is_active == True
            )
            result = await db.execute(query)
            existing_primary = result.scalars().all()
            for assignment in existing_primary:
                assignment.is_primary = False
                assignment.updated_at = datetime.now(timezone.utc)

        # Create assignment
        db_assignment = UserDepartments(
            user_id=user_department.user_id,
            department_id=user_department.department_id,
            is_primary=user_department.is_primary,
            assigned_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_assignment)
        await db.commit()
        await db.refresh(db_assignment)

        logger.info(f"User department assignment created, user_department_id: {db_assignment.user_department_id}, user_id: {db_assignment.user_id}")
        return UserDepartmentOut.model_validate(db_assignment)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user department assignment: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating user department assignment")

@router.get("/{user_department_id}", response_model=UserDepartmentOut, summary="Get user department assignment by ID")
async def read_user_department(
    user_department_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserDepartmentOut:
    """Get a user department assignment by ID. Requires MANAGE_DEPARTMENTS permission or viewing own assignment."""
    try:
        # Get the assignment first to check ownership
        query = select(UserDepartments).where(UserDepartments.user_department_id == user_department_id, UserDepartments.is_active == True, UserDepartments.deleted_at == None)
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()

        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User department assignment not found")

        # Allow users to view their own department assignments
        if assignment.user_id != current_user.user_id:
            await check_permissions([Permission.MANAGE_DEPARTMENTS.value], current_user, db)

        logger.info(f"Retrieved user department assignment, user_department_id: {user_department_id}")
        return UserDepartmentOut.model_validate(assignment)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user department assignment {user_department_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving user department assignment")

@router.get("/", response_model=List[UserDepartmentOut], summary="List user department assignments")
async def read_user_departments(
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[UserDepartmentOut]:
    """List user department assignments with optional filters. Requires MANAGE_DEPARTMENTS permission."""
    try:
        await check_permissions([Permission.MANAGE_DEPARTMENTS.value], current_user, db)

        query = select(UserDepartments).where(UserDepartments.is_active == True, UserDepartments.deleted_at == None)
        if user_id:
            query = query.where(UserDepartments.user_id == user_id)
        if department_id:
            query = query.where(UserDepartments.department_id == department_id)
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        assignments = result.scalars().all()

        logger.info(f"Retrieved {len(assignments)} user department assignments")
        return [UserDepartmentOut.model_validate(assignment) for assignment in assignments]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user department assignments: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving user department assignments")

@router.put("/{user_department_id}", response_model=UserDepartmentOut, summary="Update user department assignment")
async def update_user_department(
    user_department_id: int,
    user_department_update: UserDepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserDepartmentOut:
    """Update a user department assignment. Requires MANAGE_DEPARTMENTS permission."""
    try:
        await check_permissions([Permission.MANAGE_DEPARTMENTS.value], current_user, db)

        # Get existing assignment
        query = select(UserDepartments).where(UserDepartments.user_department_id == user_department_id, UserDepartments.is_active == True, UserDepartments.deleted_at == None)
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()

        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User department assignment not found")

        update_data = user_department_update.model_dump(exclude_none=True)
        
        # Validate user if being updated
        if "user_id" in update_data:
            query = select(Users).where(Users.user_id == update_data["user_id"], Users.is_active == True, Users.deleted_at == None)
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Validate department if being updated
        if "department_id" in update_data:
            query = select(Departments).where(Departments.department_id == update_data["department_id"], Departments.is_active == True, Departments.deleted_at == None)
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

        # Check for duplicate assignment if user_id or department_id changing
        if update_data.get("user_id") or update_data.get("department_id"):
            query = select(UserDepartments).where(
                UserDepartments.user_id == update_data.get("user_id", assignment.user_id),
                UserDepartments.department_id == update_data.get("department_id", assignment.department_id),
                UserDepartments.is_active == True,
                UserDepartments.user_department_id != user_department_id
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User department assignment already exists")

        # Handle primary department changes
        if "is_primary" in update_data and update_data["is_primary"]:
            user_id_to_update = update_data.get("user_id", assignment.user_id)
            # Set other primary departments to non-primary
            query = select(UserDepartments).where(
                UserDepartments.user_id == user_id_to_update,
                UserDepartments.is_primary == True,
                UserDepartments.is_active == True,
                UserDepartments.user_department_id != user_department_id
            )
            result = await db.execute(query)
            existing_primary = result.scalars().all()
            for other_assignment in existing_primary:
                other_assignment.is_primary = False
                other_assignment.updated_at = datetime.now(timezone.utc)

        # Apply updates
        for key, value in update_data.items():
            setattr(assignment, key, value)

        assignment.updated_at = datetime.now(timezone.utc)
        db.add(assignment)
        await db.commit()
        await db.refresh(assignment)

        logger.info(f"User department assignment updated, user_department_id: {user_department_id}")
        return UserDepartmentOut.model_validate(assignment)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user department assignment {user_department_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating user department assignment")

@router.delete("/{user_department_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete user department assignment")
async def delete_user_department(
    user_department_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    """Soft delete a user department assignment. Requires MANAGE_DEPARTMENTS permission."""
    try:
        await check_permissions([Permission.MANAGE_DEPARTMENTS.value], current_user, db)

        query = select(UserDepartments).where(UserDepartments.user_department_id == user_department_id, UserDepartments.is_active == True, UserDepartments.deleted_at == None)
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()

        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User department assignment not found")

        # Prevent deletion of user's last department assignment
        query = select(UserDepartments).where(
            UserDepartments.user_id == assignment.user_id,
            UserDepartments.is_active == True,
            UserDepartments.deleted_at == None
        )
        result = await db.execute(query)
        user_departments = result.scalars().all()
        
        if len(user_departments) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete user's last department assignment"
            )

        # Soft delete
        assignment.is_active = False
        assignment.deleted_at = datetime.now(timezone.utc)
        assignment.updated_at = datetime.now(timezone.utc)
        
        await db.commit()

        logger.info(f"User department assignment soft deleted, user_department_id: {user_department_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user department assignment {user_department_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting user department assignment")

# Additional endpoint to get user's departments
@router.get("/user/{user_id}/departments", response_model=List[UserDepartmentOut], summary="Get all departments for a user")
async def get_user_departments(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[UserDepartmentOut]:
    """Get all active departments for a specific user. Requires MANAGE_DEPARTMENTS permission or viewing own departments."""
    try:
        # Allow users to view their own departments
        if current_user.user_id != user_id:
            await check_permissions([Permission.MANAGE_DEPARTMENTS.value], current_user, db)

        query = select(UserDepartments).where(
            UserDepartments.user_id == user_id,
            UserDepartments.is_active == True,
            UserDepartments.deleted_at == None
        )
        result = await db.execute(query)
        assignments = result.scalars().all()

        return [UserDepartmentOut.model_validate(assignment) for assignment in assignments]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving departments for user {user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving user departments")