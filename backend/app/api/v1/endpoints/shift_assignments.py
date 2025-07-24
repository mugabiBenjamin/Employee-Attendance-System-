from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import AsyncGenerator, List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone, date
from app.core.database import AsyncSessionLocal
from app.models.shift_assignments import ShiftAssignments
from app.models.shift_patterns import ShiftPatterns
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.core.security import check_user_permission
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shift-assignments", tags=["Shift Assignments"])

class ShiftAssignmentCreate(BaseModel):
    """Schema for creating a new shift assignment."""
    user_id: int
    shift_pattern_id: int
    start_date: date
    end_date: Optional[date] = None

    model_config = ConfigDict(from_attributes=True)

class ShiftAssignmentUpdate(BaseModel):
    """Schema for updating an existing shift assignment."""
    user_id: Optional[int] = None
    shift_pattern_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    model_config = ConfigDict(from_attributes=True)

class ShiftAssignmentOut(BaseModel):
    """Schema for shift assignment output."""
    assignment_id: int
    user_id: int
    shift_pattern_id: int
    start_date: date
    end_date: Optional[date]
    created_at: datetime
    updated_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to provide an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {str(e)}")
            await session.rollback()
            raise
        finally:
            await session.close()

async def get_current_active_user(db: AsyncSession = Depends(get_db)) -> Users:
    """Dependency to get the current active user."""
    query = select(Users).where(Users.is_active == True, Users.deleted_at == None)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")
    return user

async def is_admin_or_manager(db: AsyncSession, user: Users) -> bool:
    """
    Check if the user has Manager, HR, Admin, or Super_Admin role.

    Args:
        db: Async database session.
        user: Current user object.

    Returns:
        bool: True if user has required role, False otherwise.
    """
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

@router.post("/", response_model=ShiftAssignmentOut, status_code=status.HTTP_201_CREATED, summary="Create new shift assignment", description="Create a new shift assignment. Requires manage_shift_assignments permission or manager/admin access.")
async def create_shift_assignment(
    shift_assignment: ShiftAssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> ShiftAssignmentOut:
    """
    Create a new shift assignment in the system.

    Args:
        shift_assignment: Shift assignment creation data.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        ShiftAssignmentOut: Created shift assignment details.

    Raises:
        HTTPException: If user lacks permission, user or shift pattern not found, or assignment conflicts.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "manage_shift_assignments")
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create shift assignments")

        # Verify user exists
        query = select(Users).where(
            Users.user_id == shift_assignment.user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Verify shift pattern exists
        query = select(ShiftPatterns).where(
            ShiftPatterns.shift_pattern_id == shift_assignment.shift_pattern_id,
            ShiftPatterns.is_active == True,
            ShiftPatterns.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift pattern not found")

        # Check for conflicting assignments
        query = select(ShiftAssignments).where(
            ShiftAssignments.user_id == shift_assignment.user_id,
            ShiftAssignments.is_active == True,
            ShiftAssignments.start_date <= (shift_assignment.end_date or shift_assignment.start_date),
            (ShiftAssignments.end_date >= shift_assignment.start_date) | (ShiftAssignments.end_date == None)
        )
        result = await db.execute(query)
        if result.scalars().first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Conflicting shift assignment exists")

        db_assignment = ShiftAssignments(
            **shift_assignment.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_assignment)
        await db.commit()
        await db.refresh(db_assignment)

        logger.info(f"Shift assignment created, assignment_id: {db_assignment.assignment_id}, user_id: {db_assignment.user_id}")
        return ShiftAssignmentOut.model_validate(db_assignment)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating shift assignment: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating shift assignment")

@router.get("/{assignment_id}", response_model=ShiftAssignmentOut, summary="Get shift assignment by ID", description="Retrieve shift assignment details. Requires view_shift_assignments permission or manager/admin access.")
async def read_shift_assignment(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> ShiftAssignmentOut:
    """
    Get a specific shift assignment by its ID.

    Args:
        assignment_id: ID of the shift assignment to retrieve.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        ShiftAssignmentOut: Shift assignment details.

    Raises:
        HTTPException: If user lacks permission or shift assignment not found.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "view_shift_assignments")
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view shift assignments")

        query = select(ShiftAssignments).where(
            ShiftAssignments.assignment_id == assignment_id,
            ShiftAssignments.is_active == True,
            ShiftAssignments.deleted_at == None
        )
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()

        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift assignment not found")

        logger.info(f"Retrieved shift assignment, assignment_id: {assignment_id}")
        return ShiftAssignmentOut.model_validate(assignment)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving shift assignment {assignment_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving shift assignment")

@router.get("/", response_model=List[ShiftAssignmentOut], summary="List all shift assignments", description="Retrieve all shift assignments with pagination. Requires view_shift_assignments permission or manager/admin access.")
async def read_shift_assignments(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[ShiftAssignmentOut]:
    """
    Get a paginated list of shift assignments, optionally filtered by user.

    Args:
        user_id: Optional user ID to filter assignments.
        skip: Number of records to skip (for pagination).
        limit: Maximum number of records to return.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        List[ShiftAssignmentOut]: List of shift assignment details.

    Raises:
        HTTPException: If user lacks permission or an error occurs.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "view_shift_assignments")
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view shift assignments")

        query = select(ShiftAssignments).where(
            ShiftAssignments.is_active == True,
            ShiftAssignments.deleted_at == None
        )
        if user_id:
            query = query.where(ShiftAssignments.user_id == user_id)
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        assignments = result.scalars().all()

        logger.info(f"Retrieved {len(assignments)} shift assignments")
        return [ShiftAssignmentOut.model_validate(assignment) for assignment in assignments]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving shift assignments: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving shift assignments")

@router.put("/{assignment_id}", response_model=ShiftAssignmentOut, summary="Update shift assignment", description="Update shift assignment information. Requires manage_shift_assignments permission or manager/admin access.")
async def update_shift_assignment(
    assignment_id: int,
    shift_assignment_update: ShiftAssignmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> ShiftAssignmentOut:
    """
    Update an existing shift assignment's information.

    Args:
        assignment_id: ID of the shift assignment to update.
        shift_assignment_update: Updated shift assignment data.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        ShiftAssignmentOut: Updated shift assignment details.

    Raises:
        HTTPException: If user lacks permission, assignment not found, or conflicts exist.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "manage_shift_assignments")
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update shift assignments")

        query = select(ShiftAssignments).where(
            ShiftAssignments.assignment_id == assignment_id,
            ShiftAssignments.is_active == True,
            ShiftAssignments.deleted_at == None
        )
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()

        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift assignment not found")

        update_data = shift_assignment_update.model_dump(exclude_none=True)
        if "user_id" in update_data:
            query = select(Users).where(
                Users.user_id == update_data["user_id"],
                Users.is_active == True,
                Users.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if "shift_pattern_id" in update_data:
            query = select(ShiftPatterns).where(
                ShiftPatterns.shift_pattern_id == update_data["shift_pattern_id"],
                ShiftPatterns.is_active == True,
                ShiftPatterns.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift pattern not found")

        if update_data.get("user_id") or update_data.get("start_date") or update_data.get("end_date"):
            query = select(ShiftAssignments).where(
                ShiftAssignments.user_id == update_data.get("user_id", assignment.user_id),
                ShiftAssignments.is_active == True,
                ShiftAssignments.assignment_id != assignment_id,
                ShiftAssignments.start_date <= (update_data.get("end_date", assignment.end_date) or update_data.get("start_date", assignment.start_date)),
                (ShiftAssignments.end_date >= update_data.get("start_date", assignment.start_date)) | (ShiftAssignments.end_date == None)
            )
            result = await db.execute(query)
            if result.scalars().first():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Conflicting shift assignment exists")

        for key, value in update_data.items():
            setattr(assignment, key, value)

        assignment.updated_at = datetime.now(timezone.utc)
        db.add(assignment)
        await db.commit()
        await db.refresh(assignment)

        logger.info(f"Shift assignment updated, assignment_id: {assignment_id}")
        return ShiftAssignmentOut.model_validate(assignment)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating shift assignment {assignment_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating shift assignment")

@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete shift assignment", description="Soft delete a shift assignment. Requires manage_shift_assignments permission or manager/admin access.")
async def delete_shift_assignment(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    """
    Soft delete a shift assignment from the system.

    Args:
        assignment_id: ID of the shift assignment to delete.
        db: Async database session.
        current_user: Current authenticated user.

    Raises:
        HTTPException: If user lacks permission or shift assignment not found.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "manage_shift_assignments")
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete shift assignments")

        query = select(ShiftAssignments).where(
            ShiftAssignments.assignment_id == assignment_id,
            ShiftAssignments.is_active == True,
            ShiftAssignments.deleted_at == None
        )
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()

        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift assignment not found")

        assignment.is_active = False
        assignment.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Shift assignment soft deleted, assignment_id: {assignment_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting shift assignment {assignment_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting shift assignment")