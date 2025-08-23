from fastapi import APIRouter, Depends, status, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.services.shift_assignment_service import (
    create_shift_assignment,
    read_shift_assignment,
    read_shift_assignments,
    update_shift_assignment,
    delete_shift_assignment,
    get_my_shift_assignments
)
from app.schemas.shift_assignment import ShiftAssignmentCreate, ShiftAssignmentUpdate, ShiftAssignmentOut
from app.core.permissions import require_permissions
from app.core.utils import get_request_id
from app.core.enums import Permission
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shift-assignments", tags=["Shift Assignments"])

@router.post(
    "/",
    response_model=ShiftAssignmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new shift assignment",
    description="Create a new shift assignment for a user with specified shift pattern and effective dates."
)
async def create_shift_assignment_endpoint(
    shift_assignment: ShiftAssignmentCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.CREATE_SHIFT_ASSIGNMENT]))
) -> ShiftAssignmentOut:
    """Create a new shift assignment.

    Args:
        shift_assignment: The shift assignment data to create.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        ShiftAssignmentOut: The created shift assignment.

    Raises:
        HTTPException: For validation errors (422), not found (404), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
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
async def read_shift_assignment_endpoint(
    assignment_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_SHIFT_ASSIGNMENT, Permission.VIEW_OWN_SHIFT_ASSIGNMENT]))
) -> ShiftAssignmentOut:
    """Retrieve a shift assignment by ID.

    Args:
        assignment_id: The ID of the shift assignment to retrieve.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        ShiftAssignmentOut: The retrieved shift assignment.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await read_shift_assignment(assignment_id, current_user, db, settings, request_id)
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
    description="List shift assignments with optional filtering by user ID, pattern ID, or department ID, and pagination."
)
async def read_shift_assignments_endpoint(
    user_id: Optional[int] = None,
    pattern_id: Optional[int] = None,
    department_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    request: Request = Depends(),
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_SHIFT_ASSIGNMENT, Permission.VIEW_OWN_SHIFT_ASSIGNMENT]))
) -> List[ShiftAssignmentOut]:
    """List shift assignments with optional filters and pagination.

    Args:
        user_id: Optional user ID to filter assignments.
        pattern_id: Optional shift pattern ID to filter assignments.
        department_id: Optional department ID to filter assignments by user department.
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: DEFAULT_PAGE_SIZE).
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[ShiftAssignmentOut]: List of shift assignments.

    Raises:
        HTTPException: For validation errors (422), not found (404), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await read_shift_assignments(user_id, pattern_id, department_id, skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error listing shift assignments: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing shift assignments: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{assignment_id}",
    response_model=ShiftAssignmentOut,
    summary="Update a shift assignment",
    description="Update an existing shift assignment with new details."
)
async def update_shift_assignment_endpoint(
    assignment_id: int,
    shift_assignment_update: ShiftAssignmentUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.UPDATE_SHIFT_ASSIGNMENT]))
) -> ShiftAssignmentOut:
    """Update a shift assignment.

    Args:
        assignment_id: The ID of the shift assignment to update.
        shift_assignment_update: The updated shift assignment data.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        ShiftAssignmentOut: The updated shift assignment.

    Raises:
        HTTPException: For validation errors (422), not found (404), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await update_shift_assignment(assignment_id, shift_assignment_update, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error updating shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating shift assignment {assignment_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a shift assignment",
    description="Soft delete a shift assignment."
)
async def delete_shift_assignment_endpoint(
    assignment_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.DELETE_SHIFT_ASSIGNMENT]))
) -> None:
    """Soft delete a shift assignment.

    Args:
        assignment_id: The ID of the shift assignment to delete.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        None: No content returned on successful deletion.

    Raises:
        HTTPException: For validation errors (422), not found (404), business logic errors (422), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        await delete_shift_assignment(assignment_id, request, current_user, db, settings, request_id)
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
async def get_my_shift_assignments_endpoint(
    skip: int = 0,
    limit: Optional[int] = None,
    request: Request = Depends(),
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_OWN_SHIFT_ASSIGNMENT]))
) -> List[ShiftAssignmentOut]:
    """Retrieve the current user's shift assignments.

    Args:
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: DEFAULT_PAGE_SIZE).
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[ShiftAssignmentOut]: List of the user's shift assignments.

    Raises:
        HTTPException: For validation errors (422), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await get_my_shift_assignments(skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving shift assignments for user {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving shift assignments for user {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")