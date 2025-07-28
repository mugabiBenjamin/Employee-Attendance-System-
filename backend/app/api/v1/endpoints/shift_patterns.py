from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timezone
from app.core.database import get_db
from app.models.shift_patterns import ShiftPatterns
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.core.permissions import check_permissions
from app.core.security import get_current_active_user
from app.core.config import settings
from app.core.enums import Permission
from app.schemas.shift_pattern import ShiftPatternCreate, ShiftPatternUpdate, ShiftPatternOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shift-patterns", tags=["Shift Patterns"])

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

@router.post("/", response_model=ShiftPatternOut, status_code=status.HTTP_201_CREATED, summary="Create new shift pattern")
async def create_shift_pattern(
    shift_pattern: ShiftPatternCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> ShiftPatternOut:
    try:
        has_permission = await check_permissions([Permission.MANAGE_SHIFT_PATTERNS.value], current_user, db)
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create shift patterns")

        query = select(ShiftPatterns).where(ShiftPatterns.pattern_name == shift_pattern.pattern_name, ShiftPatterns.is_active == True)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shift pattern name already exists")

        db_shift_pattern = ShiftPatterns(
            pattern_name=shift_pattern.pattern_name,
            shift_type=shift_pattern.shift_type,
            start_time=shift_pattern.start_time,
            end_time=shift_pattern.end_time,
            break_duration=shift_pattern.break_duration,
            is_overnight=shift_pattern.is_overnight,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_shift_pattern)
        await db.commit()
        await db.refresh(db_shift_pattern)

        logger.info(f"Shift pattern created, pattern_id: {db_shift_pattern.pattern_id}, name: {db_shift_pattern.pattern_name}")
        return ShiftPatternOut.model_validate(db_shift_pattern)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating shift pattern: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating shift pattern")

@router.get("/{pattern_id}", response_model=ShiftPatternOut, summary="Get shift pattern by ID")
async def read_shift_pattern(
    pattern_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> ShiftPatternOut:
    try:
        has_permission = await check_permissions([Permission.VIEW_SHIFT_PATTERNS.value], current_user, db)
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view shift patterns")

        query = select(ShiftPatterns).where(ShiftPatterns.pattern_id == pattern_id, ShiftPatterns.is_active == True, ShiftPatterns.deleted_at == None)
        result = await db.execute(query)
        shift_pattern = result.scalar_one_or_none()

        if not shift_pattern:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift pattern not found")

        logger.info(f"Retrieved shift pattern, pattern_id: {pattern_id}")
        return ShiftPatternOut.model_validate(shift_pattern)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving shift pattern {pattern_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving shift pattern")

@router.get("/", response_model=List[ShiftPatternOut], summary="List all shift patterns")
async def read_shift_patterns(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[ShiftPatternOut]:
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

@router.put("/{pattern_id}", response_model=ShiftPatternOut, summary="Update shift pattern")
async def update_shift_pattern(
    pattern_id: int,
    shift_pattern_update: ShiftPatternUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> ShiftPatternOut:
    try:
        has_permission = await check_permissions([Permission.MANAGE_SHIFT_PATTERNS.value], current_user, db)
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update shift patterns")

        query = select(ShiftPatterns).where(ShiftPatterns.pattern_id == pattern_id, ShiftPatterns.is_active == True, ShiftPatterns.deleted_at == None)
        result = await db.execute(query)
        shift_pattern = result.scalar_one_or_none()

        if not shift_pattern:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift pattern not found")

        update_data = shift_pattern_update.model_dump(exclude_none=True)
        if "pattern_name" in update_data and update_data["pattern_name"] != shift_pattern.pattern_name:
            query = select(ShiftPatterns).where(ShiftPatterns.pattern_name == update_data["pattern_name"], ShiftPatterns.is_active == True)
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shift pattern name already exists")

        for key, value in update_data.items():
            setattr(shift_pattern, key, value)

        shift_pattern.updated_at = datetime.now(timezone.utc)
        db.add(shift_pattern)
        await db.commit()
        await db.refresh(shift_pattern)

        logger.info(f"Shift pattern updated, pattern_id: {pattern_id}")
        return ShiftPatternOut.model_validate(shift_pattern)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating shift pattern {pattern_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating shift pattern")

@router.delete("/{pattern_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete shift pattern")
async def delete_shift_pattern(
    pattern_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    try:
        has_permission = await check_permissions([Permission.MANAGE_SHIFT_PATTERNS.value], current_user, db)
        if not has_permission and not await is_admin_or_manager(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete shift patterns")

        query = select(ShiftPatterns).where(ShiftPatterns.pattern_id == pattern_id, ShiftPatterns.is_active == True, ShiftPatterns.deleted_at == None)
        result = await db.execute(query)
        shift_pattern = result.scalar_one_or_none()

        if not shift_pattern:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift pattern not found")

        shift_pattern.is_active = False
        shift_pattern.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Shift pattern soft deleted, pattern_id: {pattern_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting shift pattern {pattern_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting shift pattern")