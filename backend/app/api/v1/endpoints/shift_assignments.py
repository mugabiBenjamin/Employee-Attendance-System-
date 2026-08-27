from fastapi import APIRouter, Depends, Request
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
from app.core.permissions import require_permissions_dependency
from app.core.utils import get_request_id
from app.core.enums import Permission

router = APIRouter(prefix="/shift-assignments", tags=["Shift Assignments"])

@router.post(
    "/",
    response_model=ShiftAssignmentOut,
    status_code=201,
    summary="Create a new shift assignment"
)
async def create_shift_assignment_endpoint(
    shift_assignment: ShiftAssignmentCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.CREATE_SHIFT_ASSIGNMENT]))
) -> ShiftAssignmentOut:
    """Create a new shift assignment."""
    request_id = get_request_id(request)
    return await create_shift_assignment(shift_assignment, request, current_user, db, settings, request_id)

@router.get(
    "/{assignment_id}",
    response_model=ShiftAssignmentOut,
    summary="Get shift assignment by ID"
)
async def read_shift_assignment_endpoint(
    assignment_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_SHIFT_ASSIGNMENT, Permission.VIEW_OWN_SHIFT_ASSIGNMENT]))
) -> ShiftAssignmentOut:
    """Retrieve a shift assignment by ID."""
    request_id = get_request_id(request)
    return await read_shift_assignment(assignment_id, current_user, db, settings, request_id)

@router.get(
    "/",
    response_model=List[ShiftAssignmentOut],
    summary="List shift assignments"
)
async def read_shift_assignments_endpoint(
    request: Request,
    user_id: Optional[int] = None,
    pattern_id: Optional[int] = None,
    department_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_SHIFT_ASSIGNMENT, Permission.VIEW_OWN_SHIFT_ASSIGNMENT]))
) -> List[ShiftAssignmentOut]:
    """List shift assignments with optional filters and pagination."""
    request_id = get_request_id(request)
    return await read_shift_assignments(user_id, pattern_id, department_id, skip, limit, current_user, db, settings, request_id)

@router.put(
    "/{assignment_id}",
    response_model=ShiftAssignmentOut,
    summary="Update a shift assignment"
)
async def update_shift_assignment_endpoint(
    assignment_id: int,
    shift_assignment_update: ShiftAssignmentUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.UPDATE_SHIFT_ASSIGNMENT]))
) -> ShiftAssignmentOut:
    """Update a shift assignment."""
    request_id = get_request_id(request)
    return await update_shift_assignment(assignment_id, shift_assignment_update, request, current_user, db, settings, request_id)

@router.delete(
    "/{assignment_id}",
    status_code=204,
    summary="Delete a shift assignment"
)
async def delete_shift_assignment_endpoint(
    assignment_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.DELETE_SHIFT_ASSIGNMENT]))
) -> None:
    """Soft delete a shift assignment."""
    request_id = get_request_id(request)
    await delete_shift_assignment(assignment_id, request, current_user, db, settings, request_id)

@router.get(
    "/my/shifts",
    response_model=List[ShiftAssignmentOut],
    summary="Get current user's shift assignments"
)
async def get_my_shift_assignments_endpoint(
    request: Request,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_OWN_SHIFT_ASSIGNMENT]))
) -> List[ShiftAssignmentOut]:
    """Retrieve the current user's shift assignments."""
    request_id = get_request_id(request)
    return await get_my_shift_assignments(skip, limit, current_user, db, settings, request_id)