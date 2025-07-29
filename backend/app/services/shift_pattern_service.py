from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, time
from app.models.shift_patterns import ShiftPatterns
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.schemas.shift_pattern import ShiftPatternCreate, ShiftPatternUpdate, ShiftPatternOut
from app.core.config import settings
from app.core.enums import SystemAction
import logging

logger = logging.getLogger(__name__)

async def create_shift_pattern(db: AsyncSession, shift_pattern: ShiftPatternCreate, current_user: Users) -> ShiftPatternOut:
    """
    Create a new shift pattern with validation and logging.
    """
    try:
        # Check for existing shift pattern with same name
        query = select(ShiftPatterns).where(
            ShiftPatterns.pattern_name == shift_pattern.shift_name,
            ShiftPatterns.is_active == True,
            ShiftPatterns.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Shift pattern name already exists"
            )

        # Create shift pattern
        start_time = datetime.strptime(shift_pattern.start_time, "%H:%M:%S").time() if isinstance(shift_pattern.start_time, str) else shift_pattern.start_time
        end_time = datetime.strptime(shift_pattern.end_time, "%H:%M:%S").time() if isinstance(shift_pattern.end_time, str) else shift_pattern.end_time
        db_shift_pattern = ShiftPatterns(
            pattern_name=shift_pattern.shift_name,
            shift_type=shift_pattern.shift_type or "standard",
            start_time=start_time,
            end_time=end_time,
            break_duration=shift_pattern.break_duration or 0,
            is_overnight=shift_pattern.is_overnight or False,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_shift_pattern)
        await db.commit()
        await db.refresh(db_shift_pattern)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="shift_patterns",
            record_id=db_shift_pattern.pattern_id,
            old_values=None,
            new_values=db_shift_pattern.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Shift pattern created, pattern_id: {db_shift_pattern.pattern_id}, name: {db_shift_pattern.pattern_name}")
        return ShiftPatternOut.model_validate(db_shift_pattern)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating shift pattern: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating shift pattern"
        )

async def get_shift_pattern_by_id(db: AsyncSession, shift_id: int) -> Optional[ShiftPatternOut]:
    """
    Retrieve a shift pattern by ID.
    """
    try:
        query = select(ShiftPatterns).where(
            ShiftPatterns.pattern_id == shift_id,
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
        logger.error(f"Error retrieving shift pattern {shift_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving shift pattern"
        )

async def get_shift_patterns(db: AsyncSession, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[ShiftPatternOut]:
    """
    Retrieve a list of active shift patterns with pagination.
    """
    try:
        query = select(ShiftPatterns).where(
            ShiftPatterns.is_active == True,
            ShiftPatterns.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        shift_patterns = result.scalars().all()

        logger.info(f"Retrieved {len(shift_patterns)} shift patterns")
        return [ShiftPatternOut.model_validate(pattern) for pattern in shift_patterns]

    except Exception as e:
        logger.error(f"Error retrieving shift patterns: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving shift patterns"
        )

async def update_shift_pattern(db: AsyncSession, shift_id: int, shift_pattern_update: ShiftPatternUpdate, current_user: Users) -> ShiftPatternOut:
    """
    Update a shift pattern with validation and logging.
    """
    try:
        # Retrieve shift pattern
        query = select(ShiftPatterns).where(
            ShiftPatterns.pattern_id == shift_id,
            ShiftPatterns.is_active == True,
            ShiftPatterns.deleted_at == None
        )
        result = await db.execute(query)
        db_shift_pattern = result.scalar_one_or_none()

        if not db_shift_pattern:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shift pattern not found"
            )

        # Check for duplicate shift name if updated
        update_data = shift_pattern_update.model_dump(exclude_none=True)
        if "pattern_name" in update_data:
            query = select(ShiftPatterns).where(
                ShiftPatterns.pattern_name == update_data["pattern_name"],
                ShiftPatterns.pattern_id != shift_id,
                ShiftPatterns.is_active == True,
                ShiftPatterns.deleted_at == None
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Shift pattern name already exists"
                )

        # Apply updates
        for key, value in update_data.items():
            setattr(db_shift_pattern, key, value)

        db_shift_pattern.updated_at = datetime.now(timezone.utc)
        db.add(db_shift_pattern)
        await db.commit()
        await db.refresh(db_shift_pattern)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE,
            table_affected="shift_patterns",
            record_id=shift_id,
            old_values=None,
            new_values=db_shift_pattern.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Shift pattern updated, pattern_id: {shift_id}")
        return ShiftPatternOut.model_validate(db_shift_pattern)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating shift pattern {shift_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating shift pattern"
        )

async def delete_shift_pattern(db: AsyncSession, shift_id: int, current_user: Users) -> None:
    """
    Soft delete a shift pattern with logging.
    """
    try:
        query = select(ShiftPatterns).where(
            ShiftPatterns.pattern_id == shift_id,
            ShiftPatterns.is_active == True,
            ShiftPatterns.deleted_at == None
        )
        result = await db.execute(query)
        db_shift_pattern = result.scalar_one_or_none()

        if not db_shift_pattern:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shift pattern not found"
            )

        db_shift_pattern.is_active = False
        db_shift_pattern.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.DELETE,
            table_affected="shift_patterns",
            record_id=shift_id,
            old_values=db_shift_pattern.__dict__,
            new_values=None,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Shift pattern soft deleted, pattern_id: {shift_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting shift pattern {shift_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting shift pattern"
        )