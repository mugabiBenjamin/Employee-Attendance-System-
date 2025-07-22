from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from datetime import datetime, timezone, time
from app.models.shift_patterns import ShiftPattern
from app.models.shift_assignments import ShiftAssignment
from app.models.user import User
from app.schemas.user import ShiftPatternCreate, ShiftPatternUpdate, ShiftPatternOut, ShiftAssignmentCreate, ShiftAssignmentUpdate, ShiftAssignmentOut
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

async def create_shift_pattern(db: AsyncSession, shift_pattern: ShiftPatternCreate, current_user: User) -> ShiftPatternOut:
    try:
        # Validate shift_type
        valid_shift_types = ["morning", "afternoon", "night", "flexible", "split"]
        if shift_pattern.shift_type not in valid_shift_types:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"Invalid shift type. Must be one of {valid_shift_types}")
        
        # Validate time constraints
        if shift_pattern.end_time <= shift_pattern.start_time and not shift_pattern.is_overnight:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="End time must be after start time for non-overnight shifts")
        
        if shift_pattern.break_duration < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="Break duration cannot be negative")
        
        # Check for existing pattern with same name
        query = select(ShiftPattern).where(ShiftPattern.pattern_name == shift_pattern.pattern_name)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="Shift pattern name already exists")
        
        db_shift_pattern = ShiftPattern(
            **shift_pattern.model_dump(),
            created_at=datetime.now(timezone.utc)
        )
        db.add(db_shift_pattern)
        await db.commit()
        await db.refresh(db_shift_pattern)
        
        logger.info(f"Shift pattern created, pattern_id {db_shift_pattern.pattern_id}")
        return ShiftPatternOut.model_validate(db_shift_pattern)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating shift pattern: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error creating shift pattern")

async def get_shift_pattern_by_id(db: AsyncSession, pattern_id: int) -> Optional[ShiftPatternOut]:
    try:
        query = select(ShiftPattern).where(ShiftPattern.pattern_id == pattern_id, 
                                        ShiftPattern.is_active == True)
        result = await db.execute(query)
        shift_pattern = result.scalar_one_or_none()
        
        if not shift_pattern:
            return None
        
        return ShiftPatternOut.model_validate(shift_pattern)
    except Exception as e:
        logger.error(f"Error retrieving shift pattern: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error retrieving shift pattern")

async def get_shift_patterns(db: AsyncSession, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[ShiftPatternOut]:
    try:
        query = select(ShiftPattern).where(ShiftPattern.is_active == True).offset(skip).limit(limit)
        result = await db.execute(query)
        shift_patterns = result.scalars().all()
        
        logger.info(f"Retrieved {len(shift_patterns)} shift patterns")
        return [ShiftPatternOut.model_validate(pattern) for pattern in shift_patterns]
    except Exception as e:
        logger.error(f"Error retrieving shift patterns: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error retrieving shift patterns")

async def update_shift_pattern(db: AsyncSession, pattern_id: int, shift_update: ShiftPatternUpdate, 
                             current_user: User) -> ShiftPatternOut:
    try:
        query = select(ShiftPattern).where(ShiftPattern.pattern_id == pattern_id, 
                                        ShiftPattern.is_active == True)
        result = await db.execute(query)
        shift_pattern = result.scalar_one_or_none()
        
        if not shift_pattern:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                              detail="Shift pattern not found")
        
        update_data = shift_update.model_dump(exclude_none=True)
        
        # Validate shift_type if provided
        if "shift_type" in update_data:
            valid_shift_types = ["morning", "afternoon", "night", "flexible", "split"]
            if update_data["shift_type"] not in valid_shift_types:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                                  detail=f"Invalid shift type. Must be one of {valid_shift_types}")
        
        # Validate time constraints if provided
        if "start_time" in update_data or "end_time" in update_data:
            start_time = update_data.get("start_time", shift_pattern.start_time)
            end_time = update_data.get("end_time", shift_pattern.end_time)
            is_overnight = update_data.get("is_overnight", shift_pattern.is_overnight)
            if end_time <= start_time and not is_overnight:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                                  detail="End time must be after start time for non-overnight shifts")
        
        # Validate break duration if provided
        if "break_duration" in update_data and update_data["break_duration"] is not None:
            if update_data["break_duration"] < 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                                  detail="Break duration cannot be negative")
        
        # Check for duplicate pattern name
        if "pattern_name" in update_data:
            query = select(ShiftPattern).where(
                ShiftPattern.pattern_name == update_data["pattern_name"],
                ShiftPattern.pattern_id != pattern_id
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                                  detail="Shift pattern name already exists")
        
        for key, value in update_data.items():
            setattr(shift_pattern, key, value)
        
        shift_pattern.updated_at = datetime.now(timezone.utc)
        db.add(shift_pattern)
        await db.commit()
        await db.refresh(shift_pattern)
        
        logger.info(f"Shift pattern updated, pattern_id {pattern_id}")
        return ShiftPatternOut.model_validate(shift_pattern)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating shift pattern: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error updating shift pattern")

async def delete_shift_pattern(db: AsyncSession, pattern_id: int) -> None:
    try:
        query = select(ShiftPattern).where(ShiftPattern.pattern_id == pattern_id, 
                                        ShiftPattern.is_active == True)
        result = await db.execute(query)
        shift_pattern = result.scalar_one_or_none()
        
        if not shift_pattern:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                              detail="Shift pattern not found")
        
        # Check for active assignments
        query = select(ShiftAssignment).where(
            ShiftAssignment.pattern_id == pattern_id,
            ShiftAssignment.is_active == True
        )
        result = await db.execute(query)
        if result.scalars().first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="Cannot delete shift pattern with active assignments")
        
        shift_pattern.is_active = False
        await db.commit()
        
        logger.info(f"Shift pattern deleted, pattern_id {pattern_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting shift pattern: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error deleting shift pattern")

async def create_shift_assignment(db: AsyncSession, shift_assignment: ShiftAssignmentCreate, 
                                current_user: User) -> ShiftAssignmentOut:
    try:
        # Validate user
        query = select(User).where(User.user_id == shift_assignment.user_id, 
                                User.is_active == True, 
                                User.deleted_at == None)
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                              detail="User not found")
        
        # Validate shift pattern
        query = select(ShiftPattern).where(ShiftPattern.pattern_id == shift_assignment.pattern_id, 
                                        ShiftPattern.is_active == True)
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                              detail="Shift pattern not found")
        
        # Validate date range
        if shift_assignment.effective_to and shift_assignment.effective_to < shift_assignment.effective_from:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="Effective to date must be after effective from date")
        
        # Check for overlapping assignments
        query = select(ShiftAssignment).where(
            ShiftAssignment.user_id == shift_assignment.user_id,
            ShiftAssignment.is_active == True,
            (ShiftAssignment.effective_to == None) | 
            (ShiftAssignment.effective_to >= shift_assignment.effective_from)
        )
        result = await db.execute(query)
        if result.scalars().first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="User already has an active shift assignment for this period")
        
        db_assignment = ShiftAssignment(
            **shift_assignment.model_dump(),
            created_at=datetime.now(timezone.utc)
        )
        db.add(db_assignment)
        await db.commit()
        await db.refresh(db_assignment)
        
        logger.info(f"Shift assignment created, assignment_id {db_assignment.assignment_id}")
        return ShiftAssignmentOut.model_validate(db_assignment)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating shift assignment: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error creating shift assignment")

async def get_shift_assignment_by_id(db: AsyncSession, assignment_id: int) -> Optional[ShiftAssignmentOut]:
    try:
        query = select(ShiftAssignment).where(ShiftAssignment.assignment_id == assignment_id, 
                                           ShiftAssignment.is_active == True)
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()
        
        if not assignment:
            return None
        
        return ShiftAssignmentOut.model_validate(assignment)
    except Exception as e:
        logger.error(f"Error retrieving shift assignment: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error retrieving shift assignment")

async def get_shift_assignments(db: AsyncSession, user_id: Optional[int] = None, 
                              skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[ShiftAssignmentOut]:
    try:
        query = select(ShiftAssignment).where(ShiftAssignment.is_active == True)
        if user_id:
            query = query.where(ShiftAssignment.user_id == user_id)
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        assignments = result.scalars().all()
        
        logger.info(f"Retrieved {len(assignments)} shift assignments")
        return [ShiftAssignmentOut.model_validate(assignment) for assignment in assignments]
    except Exception as e:
        logger.error(f"Error retrieving shift assignments: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error retrieving shift assignments")

async def update_shift_assignment(db: AsyncSession, assignment_id: int, 
                                shift_update: ShiftAssignmentUpdate, current_user: User) -> ShiftAssignmentOut:
    try:
        query = select(ShiftAssignment).where(ShiftAssignment.assignment_id == assignment_id, 
                                           ShiftAssignment.is_active == True)
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()
        
        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                              detail="Shift assignment not found")
        
        update_data = shift_update.model_dump(exclude_none=True)
        
        # Validate pattern_id if provided
        if "pattern_id" in update_data:
            query = select(ShiftPattern).where(ShiftPattern.pattern_id == update_data["pattern_id"], 
                                            ShiftPattern.is_active == True)
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                                  detail="Shift pattern not found")
        
        # Validate date range if provided
        if "effective_to" in update_data or "effective_from" in update_data:
            effective_from = update_data.get("effective_from", assignment.effective_from)
            effective_to = update_data.get("effective_to", assignment.effective_to)
            if effective_to and effective_to < effective_from:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                                  detail="Effective to date must be after effective from date")
        
        for key, value in update_data.items():
            setattr(assignment, key, value)
        
        assignment.updated_at = datetime.now(timezone.utc)
        db.add(assignment)
        await db.commit()
        await db.refresh(assignment)
        
        logger.info(f"Shift assignment updated, assignment_id {assignment_id}")
        return ShiftAssignmentOut.model_validate(assignment)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating shift assignment: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error updating shift assignment")

async def delete_shift_assignment(db: AsyncSession, assignment_id: int) -> None:
    try:
        query = select(ShiftAssignment).where(ShiftAssignment.assignment_id == assignment_id, 
                                           ShiftAssignment.is_active == True)
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()
        
        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                              detail="Shift assignment not found")
        
        assignment.is_active = False
        await db.commit()
        
        logger.info(f"Shift assignment deleted, assignment_id {assignment_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting shift assignment: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error deleting shift assignment")