from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.shift_pattern_service import (
    create_shift_pattern as service_create_shift_pattern,
    get_shift_pattern as service_get_shift_pattern,
    list_shift_patterns as service_list_shift_patterns,
    update_shift_pattern as service_update_shift_pattern,
    delete_shift_pattern as service_delete_shift_pattern
)
from app.schemas.shift_pattern import ShiftPatternCreate, ShiftPatternUpdate, ShiftPatternOut
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
@require_permissions([Permission.CREATE_SHIFT_PATTERN])
async def create_shift_pattern_endpoint(
    shift_pattern: ShiftPatternCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> ShiftPatternOut:
    """
    Create a new shift pattern by delegating to shift_pattern_service.

    Args:
        shift_pattern: The shift pattern data to create.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        current_user: The authenticated user performing the action.
        settings: Application settings.

    Returns:
        ShiftPatternOut: The created shift pattern.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_create_shift_pattern(shift_pattern, request, current_user, db, settings, request_id)
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
@require_permissions([Permission.VIEW_SHIFT_PATTERN])
async def get_shift_pattern_endpoint(
    pattern_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> ShiftPatternOut:
    """
    Retrieve a shift pattern by ID by delegating to shift_pattern_service.

    Args:
        pattern_id: The ID of the shift pattern to retrieve.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        ShiftPatternOut: The retrieved shift pattern.

    Raises:
        HTTPException: For not found (404) or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_get_shift_pattern(pattern_id, db, settings, request_id)
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
    description="List all active shift patterns with pagination."
)
@require_permissions([Permission.VIEW_SHIFT_PATTERN])
async def list_shift_patterns_endpoint(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[ShiftPatternOut]:
    """
    List all active shift patterns by delegating to shift_pattern_service.

    Args:
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: 50).
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[ShiftPatternOut]: List of active shift patterns.

    Raises:
        HTTPException: For validation errors (422) or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_list_shift_patterns(skip, limit, db, settings, request_id)
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
@require_permissions([Permission.UPDATE_SHIFT_PATTERN])
async def update_shift_pattern_endpoint(
    pattern_id: int,
    shift_pattern_update: ShiftPatternUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> ShiftPatternOut:
    """
    Update a shift pattern by delegating to shift_pattern_service.

    Args:
        pattern_id: The ID of the shift pattern to update.
        shift_pattern_update: The updated shift pattern data.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        current_user: The authenticated user performing the action.
        settings: Application settings.

    Returns:
        ShiftPatternOut: The updated shift pattern.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_update_shift_pattern(pattern_id, shift_pattern_update, request, current_user, db, settings, request_id)
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
@require_permissions([Permission.DELETE_SHIFT_PATTERN])
async def delete_shift_pattern_endpoint(
    pattern_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> None:
    """
    Soft delete a shift pattern by delegating to shift_pattern_service.

    Args:
        pattern_id: The ID of the shift pattern to delete.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        current_user: The authenticated user performing the action.
        settings: Application settings.

    Returns:
        None: No content returned on successful deletion.

    Raises:
        HTTPException: For not found (404) or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        await service_delete_shift_pattern(pattern_id, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error deleting shift pattern {pattern_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting shift pattern {pattern_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")