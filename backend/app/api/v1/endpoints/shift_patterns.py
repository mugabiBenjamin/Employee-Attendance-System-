from fastapi import APIRouter, Depends, Request
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

router = APIRouter(prefix="/shift-patterns", tags=["Shift Patterns"])

@router.post(
    "/",
    response_model=ShiftPatternOut,
    status_code=201,
    summary="Create a new shift pattern"
)
async def create_shift_pattern_endpoint(
    shift_pattern: ShiftPatternCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.CREATE_SHIFT_PATTERN]))
) -> ShiftPatternOut:
    """Create a new shift pattern."""
    request_id = get_request_id(request)
    return await create_shift_pattern(shift_pattern, request, current_user, db, settings, request_id)

@router.get(
    "/{pattern_id}",
    response_model=ShiftPatternOut,
    summary="Get shift pattern by ID"
)
async def get_shift_pattern_endpoint(
    pattern_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_SHIFT_PATTERN]))
) -> ShiftPatternOut:
    """Retrieve a shift pattern by ID."""
    request_id = get_request_id(request)
    return await get_shift_pattern(pattern_id, db, settings, request_id)

@router.get(
    "/",
    response_model=List[ShiftPatternOut],
    summary="List all shift patterns"
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
    _=Depends(require_permissions_dependency([Permission.VIEW_SHIFT_PATTERN]))
) -> List[ShiftPatternOut]:
    """List all active shift patterns with optional filters and pagination."""
    request_id = get_request_id(request)
    return await list_shift_patterns(shift_type, department_id, skip, limit, current_user, db, settings, request_id)

@router.put(
    "/{pattern_id}",
    response_model=ShiftPatternOut,
    summary="Update a shift pattern"
)
async def update_shift_pattern_endpoint(
    pattern_id: int,
    shift_pattern_update: ShiftPatternUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.UPDATE_SHIFT_PATTERN]))
) -> ShiftPatternOut:
    """Update a shift pattern."""
    request_id = get_request_id(request)
    return await update_shift_pattern(pattern_id, shift_pattern_update, request, current_user, db, settings, request_id)

@router.delete(
    "/{pattern_id}",
    status_code=204,
    summary="Delete a shift pattern"
)
async def delete_shift_pattern_endpoint(
    pattern_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.DELETE_SHIFT_PATTERN]))
) -> None:
    """Soft delete a shift pattern."""
    request_id = get_request_id(request)
    await delete_shift_pattern(pattern_id, request, current_user, db, settings, request_id)