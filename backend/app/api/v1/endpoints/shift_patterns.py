from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import AsyncGenerator, List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone, time
from app.core.database import AsyncSessionLocal
from app.models.shift_patterns import ShiftPatterns
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.core.permissions import check_permissions
from app.core.security import get_current_active_user
from app.core.config import settings
from app.core.enums import Permission
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shift-patterns", tags=["Shift Patterns"])

class ShiftPatternCreate(BaseModel):
    """Schema for creating a new shift pattern."""
    name: str
    start_time: time
    end_time: time
    description: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class ShiftPatternUpdate(BaseModel):
    """Schema for updating an existing shift pattern."""
    name: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    description: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class ShiftPatternOut(BaseModel):
    """Schema for shift pattern output."""
    shift_pattern_id: int
    name: str
    start_time: time
    end_time: time
    description: Optional[str]
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

async def is_admin_or_manager(db: AsyncSession, user: Users) -> bool:
    """Check if user has Manager, HR, Admin, or Super_Admin role."""
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

@router.post("/", response_model=ShiftPatternOut, status_code=status.HTTP_201_CREATED, summary="Create new shift pattern")
async def create_shift_pattern(
    shift_pattern: ShiftPatternCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> ShiftPatternOut:
    """Create a new shift pattern."""
    try:
        has_permission = await check_permissions([Permission.MANAGE_SHIFT_PATTERNS.value], current_user, db)
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create shift patterns")

        query = select(ShiftPatterns).where(ShiftPatterns.name == shift_pattern.name, ShiftPatterns.is_active == True)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shift pattern name already exists")

        db_shift_pattern = ShiftPatterns(
            **shift_pattern.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_shift_pattern)
        await db.commit()
        await db.refresh(db_shift_pattern)

        logger.info(f"Shift pattern created, shift_pattern_id: {db_shift_pattern.shift_pattern_id}, name: {db_shift_pattern.name}")
        return ShiftPatternOut.model_validate(db_shift_pattern)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating shift pattern: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating shift pattern")

@router.get("/{shift_pattern_id}", response_model=ShiftPatternOut, summary="Get shift pattern by ID")
async def read_shift_pattern(
    shift_pattern_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> ShiftPatternOut:
    """Get a specific shift pattern by ID."""
    try:
        has_permission = await check_permissions([Permission.VIEW_SHIFT_PATTERNS.value], current_user, db)
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view shift patterns")

        query = select(ShiftPatterns).where(ShiftPatterns.shift_pattern_id == shift_pattern_id, ShiftPatterns.is_active == True, ShiftPatterns.deleted_at == None)
        result = await db.execute(query)
        shift_pattern = result.scalar_one_or_none()

        if not shift_pattern:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift pattern not found")

        logger.info(f"Retrieved shift pattern, shift_pattern_id: {shift_pattern_id}")
        return ShiftPatternOut.model_validate(shift_pattern)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving shift pattern {shift_pattern_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving shift pattern")

@router.get("/", response_model=List[ShiftPatternOut], summary="List all shift patterns")
async def read_shift_patterns(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[ShiftPatternOut]:
    """Get a paginated list of all shift patterns."""
    try:
        has_permission = await check_permissions([Permission.VIEW_SHIFT_PATTERNS.value], current_user, db)
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view shift patterns")

        query = select(ShiftPatterns).where(ShiftPatterns.is_active == True, ShiftPatterns.deleted_at == None).offset(skip).limit(limit)
        result = await db.execute(query)
        shift_patterns = result.scalars().all()

        logger.info(f"Retrieved {len(shift_patterns)} shift patterns")
        return [ShiftPatternOut.model_validate(pattern) for pattern in shift_patterns]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving shift patterns: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving shift patterns")

@router.put("/{shift_pattern_id}", response_model=ShiftPatternOut, summary="Update shift pattern")
async def update_shift_pattern(
    shift_pattern_id: int,
    shift_pattern_update: ShiftPatternUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> ShiftPatternOut:
    """Update an existing shift pattern."""
    try:
        has_permission = await check_permissions([Permission.MANAGE_SHIFT_PATTERNS.value], current_user, db)
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update shift patterns")

        query = select(ShiftPatterns).where(ShiftPatterns.shift_pattern_id == shift_pattern_id, ShiftPatterns.is_active == True, ShiftPatterns.deleted_at == None)
        result = await db.execute(query)
        shift_pattern = result.scalar_one_or_none()

        if not shift_pattern:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift pattern not found")

        update_data = shift_pattern_update.model_dump(exclude_none=True)
        if "name" in update_data and update_data["name"] != shift_pattern.name:
            query = select(ShiftPatterns).where(ShiftPatterns.name == update_data["name"], ShiftPatterns.is_active == True)
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shift pattern name already exists")

        for key, value in update_data.items():
            setattr(shift_pattern, key, value)

        shift_pattern.updated_at = datetime.now(timezone.utc)
        db.add(shift_pattern)
        await db.commit()
        await db.refresh(shift_pattern)

        logger.info(f"Shift pattern updated, shift_pattern_id: {shift_pattern_id}")
        return ShiftPatternOut.model_validate(shift_pattern)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating shift pattern {shift_pattern_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating shift pattern")

@router.delete("/{shift_pattern_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete shift pattern")
async def delete_shift_pattern(
    shift_pattern_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    """Soft delete a shift pattern."""
    try:
        has_permission = await check_permissions([Permission.MANAGE_SHIFT_PATTERNS.value], current_user, db)
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete shift patterns")

        query = select(ShiftPatterns).where(ShiftPatterns.shift_pattern_id == shift_pattern_id, ShiftPatterns.is_active == True, ShiftPatterns.deleted_at == None)
        result = await db.execute(query)
        shift_pattern = result.scalar_one_or_none()

        if not shift_pattern:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift pattern not found")

        shift_pattern.is_active = False
        shift_pattern.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Shift pattern soft deleted, shift_pattern_id: {shift_pattern_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting shift pattern {shift_pattern_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting shift pattern")