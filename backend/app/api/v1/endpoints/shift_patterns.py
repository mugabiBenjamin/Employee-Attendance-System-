from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.enums import Permission
from app.core.config import Settings, get_settings
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

@router.post("/", 
             response_model=ShiftPatternOut, 
             status_code=status.HTTP_201_CREATED,
             summary="Create a new shift pattern",
             description="Create a new shift pattern.")
@require_permissions([Permission.MANAGE_EMPLOYEES])
async def create_shift_pattern_endpoint(
    shift_pattern: ShiftPatternCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> ShiftPatternOut:
    """
    Create a new shift pattern by delegating to shift_pattern_service.
    """
    return await service_create_shift_pattern(shift_pattern, db, current_user, settings)

@router.get("/{pattern_id}", 
            response_model=ShiftPatternOut,
            summary="Get shift pattern by ID",
            description="Retrieve a shift pattern by its ID.")
@require_permissions([Permission.VIEW_ALL_ATTENDANCE])
async def get_shift_pattern_endpoint(
    pattern_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> ShiftPatternOut:
    """
    Retrieve a shift pattern by ID by delegating to shift_pattern_service.
    """
    return await service_get_shift_pattern(pattern_id, db, current_user, settings)

@router.get("/", 
            response_model=List[ShiftPatternOut],
            summary="List all shift patterns",
            description="List all active shift patterns with pagination.")
@require_permissions([Permission.VIEW_ALL_ATTENDANCE])
async def list_shift_patterns_endpoint(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[ShiftPatternOut]:
    """
    List all active shift patterns by delegating to shift_pattern_service.
    """
    return await service_list_shift_patterns(skip, limit, db, current_user, settings)

@router.put("/{pattern_id}", 
            response_model=ShiftPatternOut,
            summary="Update a shift pattern",
            description="Update an existing shift pattern.")
@require_permissions([Permission.MANAGE_EMPLOYEES])
async def update_shift_pattern_endpoint(
    pattern_id: int,
    shift_pattern_update: ShiftPatternUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> ShiftPatternOut:
    """
    Update a shift pattern by delegating to shift_pattern_service.
    """
    return await service_update_shift_pattern(pattern_id, shift_pattern_update, db, current_user, settings)

@router.delete("/{pattern_id}", 
               status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete a shift pattern",
               description="Soft delete a shift pattern.")
@require_permissions([Permission.MANAGE_EMPLOYEES])
async def delete_shift_pattern_endpoint(
    pattern_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> None:
    """
    Soft delete a shift pattern by delegating to shift_pattern_service.
    """
    await service_delete_shift_pattern(pattern_id, db, current_user, settings)