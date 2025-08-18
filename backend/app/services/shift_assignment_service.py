from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.shift_assignments import ShiftAssignments
from app.models.users import Users
from app.models.shift_patterns import ShiftPatterns
from app.schemas.shift_assignment import ShiftAssignmentCreate, ShiftAssignmentUpdate, ShiftAssignmentOut
from app.core.config import Settings, get_settings
from app.core.enums import Permission, SystemAction
from app.core.exceptions import UserNotFoundError, ResourceNotFoundError, ValidationError, DatabaseError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db
from app.services.system_log_service import create_system_log, SystemLogCreate
import logging

logger = logging.getLogger(__name__)

async def create_shift_assignment(
    shift_assignment: ShiftAssignmentCreate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.CREATE_SHIFT_ASSIGNMENT]))
) -> ShiftAssignmentOut:
    """
    Create a new shift assignment with validation and logging."""
    try:
        # Validate user_id
        query = select(Users).where(
            Users.user_id == shift_assignment.user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise UserNotFoundError(user_id=shift_assignment.user_id)

        # Validate pattern_id
        query = select(ShiftPatterns).where(
            ShiftPatterns.pattern_id == shift_assignment.pattern_id,
            ShiftPatterns.is_active == True
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise ResourceNotFoundError(detail=f"Shift pattern {shift_assignment.pattern_id} not found")

        # Validate effective dates
        if shift_assignment.effective_to and shift_assignment.effective_from > shift_assignment.effective_to:
            raise ValidationError(detail="effective_from cannot be after effective_to")

        # Create shift assignment
        db_assignment = ShiftAssignments(
            user_id=shift_assignment.user_id,
            pattern_id=shift_assignment.pattern_id,
            effective_from=shift_assignment.effective_from,
            effective_to=shift_assignment.effective_to,
            is_active=shift_assignment.is_active,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_assignment)
        await db.commit()
        await db.refresh(db_assignment)

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="shift_assignments",
            record_id=db_assignment.assignment_id,
            old_values=None,
            new_values=db_assignment.__dict__,
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Shift assignment created, assignment_id: {db_assignment.assignment_id}, user_id: {db_assignment.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return ShiftAssignmentOut.model_validate(db_assignment)

    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ResourceNotFoundError as e:
        logger.error(f"Resource not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error creating shift assignment: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error creating shift assignment: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def read_shift_assignment(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_SHIFT_ASSIGNMENT]))
) -> ShiftAssignmentOut:
    """
    Retrieve a shift assignment by ID."""
    try:
        query = select(ShiftAssignments).where(
            ShiftAssignments.assignment_id == assignment_id,
            ShiftAssignments.is_active == True
        )
        result = await db.execute(query)
        db_assignment = result.scalar_one_or_none()

        if not db_assignment:
            raise ResourceNotFoundError(detail=f"Shift assignment {assignment_id} not found")

        logger.info(
            f"Retrieved shift assignment, assignment_id: {assignment_id}",
            extra={"request_id": request_id}
        )
        return ShiftAssignmentOut.model_validate(db_assignment)

    except ResourceNotFoundError as e:
        logger.error(f"Shift assignment not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def read_shift_assignments(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_SHIFT_ASSIGNMENT]))
) -> List[ShiftAssignmentOut]:
    """
    Retrieve a list of shift assignments with optional user ID filter and pagination."""
    try:
        limit = limit or settings.DEFAULT_PAGE_SIZE
        if skip < 0 or limit <= 0:
            raise ValidationError(detail="Invalid pagination parameters")

        query = select(ShiftAssignments).where(ShiftAssignments.is_active == True)

        if user_id:
            query_user = select(Users).where(
                Users.user_id == user_id,
                Users.is_active == True,
                Users.deleted_at == None
            )
            result = await db.execute(query_user)
            if not result.scalar_one_or_none():
                raise UserNotFoundError(user_id=user_id)
            query = query.where(ShiftAssignments.user_id == user_id)

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        assignments = result.scalars().all()

        logger.info(
            f"Retrieved {len(assignments)} shift assignments",
            extra={"request_id": request_id, "user_id": user_id}
        )
        return [ShiftAssignmentOut.model_validate(assignment) for assignment in assignments]

    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving shift assignments: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving shift assignments: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def update_shift_assignment(
    assignment_id: int,
    shift_assignment_update: ShiftAssignmentUpdate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.UPDATE_SHIFT_ASSIGNMENT]))
) -> ShiftAssignmentOut:
    """
    Update a shift assignment with validation and logging."""
    try:
        query = select(ShiftAssignments).where(
            ShiftAssignments.assignment_id == assignment_id,
            ShiftAssignments.is_active == True
        )
        result = await db.execute(query)
        db_assignment = result.scalar_one_or_none()

        if not db_assignment:
            raise ResourceNotFoundError(detail=f"Shift assignment {assignment_id} not found")

        update_data = shift_assignment_update.model_dump(exclude_none=True)
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        if "pattern_id" in update_data:
            query = select(ShiftPatterns).where(
                ShiftPatterns.pattern_id == update_data["pattern_id"],
                ShiftPatterns.is_active == True
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise ResourceNotFoundError(detail=f"Shift pattern {update_data['pattern_id']} not found")

        if "effective_from" in update_data and "effective_to" in update_data:
            if update_data["effective_from"] > update_data["effective_to"]:
                raise ValidationError(detail="effective_from cannot be after effective_to")

        old_values = db_assignment.__dict__.copy()
        for key, value in update_data.items():
            setattr(db_assignment, key, value)

        db_assignment.updated_at = datetime.now(timezone.utc)
        db.add(db_assignment)
        await db.commit()
        await db.refresh(db_assignment)

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE,
            table_affected="shift_assignments",
            record_id=assignment_id,
            old_values=old_values,
            new_values=db_assignment.__dict__,
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Shift assignment updated, assignment_id: {assignment_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return ShiftAssignmentOut.model_validate(db_assignment)

    except ResourceNotFoundError as e:
        logger.error(f"Resource not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error updating shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error updating shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def delete_shift_assignment(
    assignment_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.DELETE_SHIFT_ASSIGNMENT]))
) -> None:
    """
    Soft delete a shift assignment with validation and logging."""
    try:
        query = select(ShiftAssignments).where(
            ShiftAssignments.assignment_id == assignment_id,
            ShiftAssignments.is_active == True
        )
        result = await db.execute(query)
        db_assignment = result.scalar_one_or_none()

        if not db_assignment:
            raise ResourceNotFoundError(detail=f"Shift assignment {assignment_id} not found")

        db_assignment.is_active = False
        db_assignment.updated_at = datetime.now(timezone.utc)
        db.add(db_assignment)
        await db.commit()

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE,
            table_affected="shift_assignments",
            record_id=assignment_id,
            old_values=db_assignment.__dict__,
            new_values=None,
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Shift assignment soft deleted, assignment_id: {assignment_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ResourceNotFoundError as e:
        logger.error(f"Shift assignment not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error deleting shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error deleting shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_my_shift_assignments(
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_OWN_SHIFT_ASSIGNMENT]))
) -> List[ShiftAssignmentOut]:
    """
    Retrieve the current user's shift assignments with pagination."""
    try:
        limit = limit or settings.DEFAULT_PAGE_SIZE
        if skip < 0 or limit <= 0:
            raise ValidationError(detail="Invalid pagination parameters")

        query = select(ShiftAssignments).where(
            ShiftAssignments.user_id == current_user.user_id,
            ShiftAssignments.is_active == True
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        assignments = result.scalars().all()

        logger.info(
            f"Retrieved {len(assignments)} shift assignments for user_id: {current_user.user_id}",
            extra={"request_id": request_id}
        )
        return [ShiftAssignmentOut.model_validate(assignment) for assignment in assignments]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving shift assignments for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving shift assignments for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")