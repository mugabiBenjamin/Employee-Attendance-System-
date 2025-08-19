from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.core.exceptions import ValidationError
from app.services.shift_assignment_service import (
    create_shift_assignment,
    read_shift_assignment,
    read_shift_assignments,
    update_shift_assignment,
    delete_shift_assignment,
    get_my_shift_assignments
)
from app.schemas.shift_assignment import ShiftAssignmentCreate, ShiftAssignmentUpdate, ShiftAssignmentOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shift-assignments", tags=["Shift Assignments"])

@router.post(
    "/",
    response_model=ShiftAssignmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create new shift assignment",
    description="Create a new shift assignment for a user."
)
@require_permissions([Permission.CREATE_SHIFT_ASSIGNMENT])
async def create_shift_assignment_endpoint(
    shift_assignment: ShiftAssignmentCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> ShiftAssignmentOut:
    """
    Create a shift assignment by delegating to shift_assignment_service.
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await create_shift_assignment(shift_assignment, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error creating shift assignment: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating shift assignment: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/{assignment_id}",
    response_model=ShiftAssignmentOut,
    summary="Get shift assignment by ID",
    description="Retrieve a specific shift assignment by its ID."
)
@require_permissions([Permission.VIEW_SHIFT_ASSIGNMENT])
async def read_shift_assignment_endpoint(
    assignment_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> ShiftAssignmentOut:
    """
    Retrieve a shift assignment by ID by delegating to shift_assignment_service.
    """
    try:
        if assignment_id <= 0:
            raise ValidationError(detail="Invalid assignment_id")
        request_id = getattr(request.state, "request_id", None)
        return await read_shift_assignment(assignment_id, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error retrieving shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/",
    response_model=List[ShiftAssignmentOut],
    summary="List shift assignments",
    description="List shift assignments, optionally filtered by user ID."
)
@require_permissions([Permission.VIEW_SHIFT_ASSIGNMENT])
async def read_shift_assignments_endpoint(
    request: Request,
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[ShiftAssignmentOut]:
    """
    List shift assignments by delegating to shift_assignment_service.
    """
    try:
        if user_id is not None and user_id <= 0:
            raise ValidationError(detail="Invalid user_id")
        request_id = getattr(request.state, "request_id", None)
        return await read_shift_assignments(user_id, skip, limit, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error listing shift assignments: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing shift assignments: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{assignment_id}",
    response_model=ShiftAssignmentOut,
    summary="Update shift assignment",
    description="Update an existing shift assignment."
)
@require_permissions([Permission.UPDATE_SHIFT_ASSIGNMENT])
async def update_shift_assignment_endpoint(
    assignment_id: int,
    shift_assignment_update: ShiftAssignmentUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> ShiftAssignmentOut:
    """
    Update a shift assignment by delegating to shift_assignment_service.
    """
    try:
        if assignment_id <= 0:
            raise ValidationError(detail="Invalid assignment_id")
        request_id = getattr(request.state, "request_id", None)
        return await update_shift_assignment(assignment_id, shift_assignment_update, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error updating shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete shift assignment",
    description="Soft delete a shift assignment."
)
@require_permissions([Permission.DELETE_SHIFT_ASSIGNMENT])
async def delete_shift_assignment_endpoint(
    assignment_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> None:
    """
    Soft delete a shift assignment by delegating to shift_assignment_service.
    """
    try:
        if assignment_id <= 0:
            raise ValidationError(detail="Invalid assignment_id")
        request_id = getattr(request.state, "request_id", None)
        await delete_shift_assignment(assignment_id, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error deleting shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/my-shifts",
    response_model=List[ShiftAssignmentOut],
    summary="Get current user's shift assignments",
    description="Retrieve the current user's shift assignments with pagination."
)
@require_permissions([Permission.VIEW_OWN_SHIFT_ASSIGNMENT])
async def get_my_shift_assignments_endpoint(
    request: Request,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> List[ShiftAssignmentOut]:
    """
    Retrieve the current user's shift assignments by delegating to shift_assignment_service.
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await get_my_shift_assignments(skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving shift assignments for user {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving shift assignments for user {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")