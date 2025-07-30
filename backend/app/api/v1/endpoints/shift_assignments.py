from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime, timezone
from app.core.database import get_db
from app.models.shift_assignments import ShiftAssignments
from app.models.shift_patterns import ShiftPatterns
from app.models.users import Users
from app.core.permissions import (
    check_permissions,
    require_permissions
)
from app.core.security import get_current_user
from app.core.config import settings
from app.core.enums import Permission
from app.schemas.shift_assignment import ShiftAssignmentCreate, ShiftAssignmentUpdate, ShiftAssignmentOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shift-assignments", tags=["Shift Assignments"])

@router.post("/", 
             response_model=ShiftAssignmentOut, 
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions([Permission.MANAGE_USERS]))],
             summary="Create new shift assignment")
async def create_shift_assignment(
    shift_assignment: ShiftAssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> ShiftAssignmentOut:
    try:
        # Verify user exists and is active
        query = select(Users).where(
            Users.user_id == shift_assignment.user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="User not found"
            )

        # Verify shift pattern exists and is active
        query = select(ShiftPatterns).where(
            ShiftPatterns.pattern_id == shift_assignment.pattern_id,
            ShiftPatterns.is_active == True,
            ShiftPatterns.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Shift pattern not found"
            )

        # Check for conflicting assignments
        query = select(ShiftAssignments).where(
            ShiftAssignments.user_id == shift_assignment.user_id,
            ShiftAssignments.is_active == True,
            ShiftAssignments.effective_from <= (shift_assignment.effective_to or shift_assignment.effective_from),
            (ShiftAssignments.effective_to >= shift_assignment.effective_from) | (ShiftAssignments.effective_to == None)
        )
        result = await db.execute(query)
        if result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Conflicting shift assignment exists for this period"
            )

        db_assignment = ShiftAssignments(
            user_id=shift_assignment.user_id,
            pattern_id=shift_assignment.pattern_id,
            effective_from=shift_assignment.effective_from,
            effective_to=shift_assignment.effective_to,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_assignment)
        await db.commit()
        await db.refresh(db_assignment)

        logger.info(f"Shift assignment created: {db_assignment.assignment_id}")
        return ShiftAssignmentOut.model_validate(db_assignment)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating shift assignment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error creating shift assignment"
        )

@router.get("/{assignment_id}", 
            response_model=ShiftAssignmentOut,
            summary="Get shift assignment by ID")
async def read_shift_assignment(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> ShiftAssignmentOut:
    try:
        # Check if user can view shift assignments
        await check_permissions([Permission.VIEW_TEAM_ATTENDANCE], current_user, db)

        query = select(ShiftAssignments).where(
            ShiftAssignments.assignment_id == assignment_id,
            ShiftAssignments.is_active == True,
            ShiftAssignments.deleted_at == None
        )
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()

        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Shift assignment not found"
            )

        logger.info(f"Retrieved shift assignment: {assignment_id}")
        return ShiftAssignmentOut.model_validate(assignment)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving shift assignment {assignment_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error retrieving shift assignment"
        )

@router.get("/", 
            response_model=List[ShiftAssignmentOut],
            summary="List shift assignments")
async def read_shift_assignments(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> List[ShiftAssignmentOut]:
    try:
        # Check permissions for viewing assignments
        if user_id and user_id != current_user.user_id:
            await check_permissions([Permission.VIEW_TEAM_ATTENDANCE], current_user, db)
        else:
            # Users can view their own assignments
            await check_permissions([Permission.VIEW_OWN_ATTENDANCE], current_user, db)

        query = select(ShiftAssignments).where(
            ShiftAssignments.is_active == True,
            ShiftAssignments.deleted_at == None
        )
        
        if user_id:
            query = query.where(ShiftAssignments.user_id == user_id)
        elif not await check_permissions([Permission.VIEW_TEAM_ATTENDANCE], current_user, db):
            # If user can't view team data, only show their own
            query = query.where(ShiftAssignments.user_id == current_user.user_id)
            
        query = query.order_by(ShiftAssignments.effective_from.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        assignments = result.scalars().all()

        logger.info(f"Retrieved {len(assignments)} shift assignments")
        return [ShiftAssignmentOut.model_validate(assignment) for assignment in assignments]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving shift assignments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error retrieving shift assignments"
        )

@router.put("/{assignment_id}", 
            response_model=ShiftAssignmentOut,
            dependencies=[Depends(require_permissions([Permission.MANAGE_USERS]))],
            summary="Update shift assignment")
async def update_shift_assignment(
    assignment_id: int,
    shift_assignment_update: ShiftAssignmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> ShiftAssignmentOut:
    try:
        query = select(ShiftAssignments).where(
            ShiftAssignments.assignment_id == assignment_id,
            ShiftAssignments.is_active == True,
            ShiftAssignments.deleted_at == None
        )
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()

        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Shift assignment not found"
            )

        update_data = shift_assignment_update.model_dump(exclude_none=True)
        
        # Validate user if being updated
        if "user_id" in update_data:
            query = select(Users).where(
                Users.user_id == update_data["user_id"],
                Users.is_active == True,
                Users.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, 
                    detail="User not found"
                )

        # Validate shift pattern if being updated
        if "pattern_id" in update_data:
            query = select(ShiftPatterns).where(
                ShiftPatterns.pattern_id == update_data["pattern_id"],
                ShiftPatterns.is_active == True,
                ShiftPatterns.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, 
                    detail="Shift pattern not found"
                )

        # Check for conflicts if dates or user are being updated
        if any(key in update_data for key in ["user_id", "effective_from", "effective_to"]):
            new_user_id = update_data.get("user_id", assignment.user_id)
            new_from = update_data.get("effective_from", assignment.effective_from)
            new_to = update_data.get("effective_to", assignment.effective_to)
            
            query = select(ShiftAssignments).where(
                ShiftAssignments.user_id == new_user_id,
                ShiftAssignments.is_active == True,
                ShiftAssignments.assignment_id != assignment_id,
                ShiftAssignments.effective_from <= (new_to or new_from),
                (ShiftAssignments.effective_to >= new_from) | (ShiftAssignments.effective_to == None)
            )
            result = await db.execute(query)
            if result.scalars().first():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="Conflicting shift assignment exists for this period"
                )

        # Apply updates
        for key, value in update_data.items():
            setattr(assignment, key, value)

        assignment.updated_at = datetime.now(timezone.utc)
        db.add(assignment)
        await db.commit()
        await db.refresh(assignment)

        logger.info(f"Shift assignment updated: {assignment_id}")
        return ShiftAssignmentOut.model_validate(assignment)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating shift assignment {assignment_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error updating shift assignment"
        )

@router.delete("/{assignment_id}", 
               status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions([Permission.MANAGE_USERS]))],
               summary="Delete shift assignment")
async def delete_shift_assignment(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> None:
    try:
        query = select(ShiftAssignments).where(
            ShiftAssignments.assignment_id == assignment_id,
            ShiftAssignments.is_active == True,
            ShiftAssignments.deleted_at == None
        )
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()

        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Shift assignment not found"
            )

        # Soft delete
        assignment.is_active = False
        assignment.deleted_at = datetime.now(timezone.utc)
        assignment.updated_at = datetime.now(timezone.utc)
        
        db.add(assignment)
        await db.commit()

        logger.info(f"Shift assignment deleted: {assignment_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting shift assignment {assignment_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error deleting shift assignment"
        )

@router.get("/my-shifts", 
            response_model=List[ShiftAssignmentOut],
            dependencies=[Depends(require_permissions([Permission.VIEW_OWN_ATTENDANCE]))],
            summary="Get current user's shift assignments")
async def get_my_shift_assignments(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> List[ShiftAssignmentOut]:
    try:
        query = select(ShiftAssignments).where(
            ShiftAssignments.user_id == current_user.user_id,
            ShiftAssignments.is_active == True,
            ShiftAssignments.deleted_at == None
        ).order_by(ShiftAssignments.effective_from.desc()).offset(skip).limit(limit)
        
        result = await db.execute(query)
        assignments = result.scalars().all()

        logger.info(f"Retrieved {len(assignments)} shift assignments for user: {current_user.user_id}")
        return [ShiftAssignmentOut.model_validate(assignment) for assignment in assignments]

    except Exception as e:
        logger.error(f"Error retrieving user shift assignments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error retrieving shift assignments"
        )