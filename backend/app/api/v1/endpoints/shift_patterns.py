from fastapi import APIRouter, Depends, status, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import ShiftType
from app.services.shift_pattern_service import (
    create_shift_pattern,
    get_shift_pattern,
    list_shift_patterns,
    update_shift_pattern,
    delete_shift_pattern
)
from app.schemas.shift_pattern import ShiftPatternCreate, ShiftPatternUpdate, ShiftPatternOut
from app.core.permissions import require_permissions_dependency
from app.core.utils import get_request_id
from app.core.enums import Permission
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shift-patterns", tags=["Shift Patterns"])

@router.post(
    "/",
    response_model=ShiftPatternOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new shift pattern",
    description="Create a new shift pattern with specified details."
)
async def create_shift_pattern_endpoint(
    shift_pattern: ShiftPatternCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _= Depends(require_permissions_dependency([Permission.CREATE_SHIFT_PATTERN]))
) -> ShiftPatternOut:
    """Create a new shift pattern.

    Args:
        shift_pattern: The shift pattern data to create.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        ShiftPatternOut: The created shift pattern.

    Raises:
        HTTPException: For validation errors (422), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await create_shift_pattern(shift_pattern, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error creating shift pattern: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating shift pattern: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/{pattern_id}",
    response_model=ShiftPatternOut,
    summary="Get shift pattern by ID",
    description="Retrieve a specific shift pattern by its ID."
)
async def get_shift_pattern_endpoint(
    pattern_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _= Depends(require_permissions_dependency([Permission.VIEW_SHIFT_PATTERN]))
) -> ShiftPatternOut:
    """Retrieve a shift pattern by ID.

    Args:
        pattern_id: The ID of the shift pattern to retrieve.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        ShiftPatternOut: The retrieved shift pattern.

    Raises:
        HTTPException: For validation errors (422), not found (404), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await get_shift_pattern(pattern_id, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving shift pattern {pattern_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving shift pattern {pattern_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/",
    response_model=List[ShiftPatternOut],
    summary="List all shift patterns",
    description="List all active shift patterns with optional filtering by shift type and department, and pagination."
)
async def list_shift_patterns_endpoint(
    request: Request,
    shift_type: Optional[ShiftType] = None,
    department_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _= Depends(require_permissions_dependency([Permission.VIEW_SHIFT_PATTERN]))
) -> List[ShiftPatternOut]:
    """List all active shift patterns with optional filters and pagination.

    Args:
        shift_type: Optional shift type to filter patterns.
        department_id: Optional department ID to filter patterns by assigned users.
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: DEFAULT_PAGE_SIZE).
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[ShiftPatternOut]: List of shift patterns.

    Raises:
        HTTPException: For validation errors (422), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await list_shift_patterns(shift_type, department_id, skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error listing shift patterns: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing shift patterns: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{pattern_id}",
    response_model=ShiftPatternOut,
    summary="Update a shift pattern",
    description="Update an existing shift pattern."
)
async def update_shift_pattern_endpoint(
    pattern_id: int,
    shift_pattern_update: ShiftPatternUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _= Depends(require_permissions_dependency([Permission.UPDATE_SHIFT_PATTERN]))
) -> ShiftPatternOut:
    """Update a shift pattern.

    Args:
        pattern_id: The ID of the shift pattern to update.
        shift_pattern_update: The updated shift pattern data.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        ShiftPatternOut: The updated shift pattern.

    Raises:
        HTTPException: For validation errors (422), not found (404), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await update_shift_pattern(pattern_id, shift_pattern_update, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error updating shift pattern {pattern_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating shift pattern {pattern_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{pattern_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a shift pattern",
    description="Soft delete a shift pattern."
)
async def delete_shift_pattern_endpoint(
    pattern_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _= Depends(require_permissions_dependency([Permission.DELETE_SHIFT_PATTERN]))
) -> None:
    """Soft delete a shift pattern.

    Args:
        pattern_id: The ID of the shift pattern to delete.
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
        await delete_shift_pattern(pattern_id, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error deleting shift pattern {pattern_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting shift pattern {pattern_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")