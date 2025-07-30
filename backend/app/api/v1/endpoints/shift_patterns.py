from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timezone
from app.core.database import get_db
from app.models.shift_patterns import ShiftPatterns
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.config import settings
from app.core.enums import Permission
from app.schemas.shift_pattern import ShiftPatternCreate, ShiftPatternUpdate, ShiftPatternOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shift-patterns", tags=["Shift Patterns"])

@router.post("/", response_model=ShiftPatternOut, status_code=status.HTTP_201_CREATED)
@require_permissions([Permission.MANAGE_EMPLOYEES])
async def create_shift_pattern(
    shift_pattern: ShiftPatternCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> ShiftPatternOut:
    """Create a new shift pattern."""
    try:
        # Check if pattern name already exists
        query = select(ShiftPatterns).where(
            ShiftPatterns.pattern_name == shift_pattern.pattern_name,
            ShiftPatterns.is_active == True
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Shift pattern name already exists"
            )

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

        logger.info(f"Created shift pattern: {db_shift_pattern.pattern_id}")
        return ShiftPatternOut.model_validate(db_shift_pattern)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating shift pattern: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating shift pattern"
        )

@router.get("/{pattern_id}", response_model=ShiftPatternOut)
@require_permissions([Permission.VIEW_ALL_ATTENDANCE])
async def get_shift_pattern(
    pattern_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> ShiftPatternOut:
    """Get shift pattern by ID."""
    try:
        query = select(ShiftPatterns).where(
            ShiftPatterns.pattern_id == pattern_id,
            ShiftPatterns.is_active == True,
            ShiftPatterns.deleted_at == None
        )
        result = await db.execute(query)
        shift_pattern = result.scalar_one_or_none()

        if not shift_pattern:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shift pattern not found"
            )

        return ShiftPatternOut.model_validate(shift_pattern)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving shift pattern {pattern_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving shift pattern"
        )

@router.get("/", response_model=List[ShiftPatternOut])
@require_permissions([Permission.VIEW_ALL_ATTENDANCE])
async def list_shift_patterns(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[ShiftPatternOut]:
    """List all active shift patterns."""
    try:
        query = select(ShiftPatterns).where(
            ShiftPatterns.is_active == True,
            ShiftPatterns.deleted_at == None
        ).offset(skip).limit(limit)
        
        result = await db.execute(query)
        shift_patterns = result.scalars().all()

        return [ShiftPatternOut.model_validate(pattern) for pattern in shift_patterns]

    except Exception as e:
        logger.error(f"Error retrieving shift patterns: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving shift patterns"
        )

@router.put("/{pattern_id}", response_model=ShiftPatternOut)
@require_permissions([Permission.MANAGE_EMPLOYEES])
async def update_shift_pattern(
    pattern_id: int,
    shift_pattern_update: ShiftPatternUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> ShiftPatternOut:
    """Update an existing shift pattern."""
    try:
        query = select(ShiftPatterns).where(
            ShiftPatterns.pattern_id == pattern_id,
            ShiftPatterns.is_active == True,
            ShiftPatterns.deleted_at == None
        )
        result = await db.execute(query)
        shift_pattern = result.scalar_one_or_none()

        if not shift_pattern:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shift pattern not found"
            )

        update_data = shift_pattern_update.model_dump(exclude_none=True)
        
        # Check for name conflicts if updating pattern_name
        if "pattern_name" in update_data and update_data["pattern_name"] != shift_pattern.pattern_name:
            query = select(ShiftPatterns).where(
                ShiftPatterns.pattern_name == update_data["pattern_name"],
                ShiftPatterns.is_active == True
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Shift pattern name already exists"
                )

        # Update fields
        for key, value in update_data.items():
            setattr(shift_pattern, key, value)

        shift_pattern.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(shift_pattern)

        logger.info(f"Updated shift pattern: {pattern_id}")
        return ShiftPatternOut.model_validate(shift_pattern)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating shift pattern {pattern_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating shift pattern"
        )

@router.delete("/{pattern_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions([Permission.MANAGE_EMPLOYEES])
async def delete_shift_pattern(
    pattern_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    """Soft delete a shift pattern."""
    try:
        query = select(ShiftPatterns).where(
            ShiftPatterns.pattern_id == pattern_id,
            ShiftPatterns.is_active == True,
            ShiftPatterns.deleted_at == None
        )
        result = await db.execute(query)
        shift_pattern = result.scalar_one_or_none()

        if not shift_pattern:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shift pattern not found"
            )

        shift_pattern.is_active = False
        shift_pattern.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Deleted shift pattern: {pattern_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting shift pattern {pattern_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting shift pattern"
        )