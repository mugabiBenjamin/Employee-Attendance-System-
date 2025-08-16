from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.shift_pattern_service import (
    create_shift_assignment as service_create_shift_assignment,
    read_shift_assignment as service_read_shift_assignment,
    read_shift_assignments as service_read_shift_assignments,
    update_shift_assignment as service_update_shift_assignment,
    delete_shift_assignment as service_delete_shift_assignment,
    get_my_shift_assignments as service_get_my_shift_assignments
)
from app.schemas.shift_assignment import ShiftAssignmentCreate, ShiftAssignmentUpdate, ShiftAssignmentOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shift-assignments", tags=["Shift Assignments"])

@router.post("/", 
            response_model=ShiftAssignmentOut, 
            status_code=status.HTTP_201_CREATED,
            dependencies=[Depends(require_permissions([Permission.MANAGE_USERS]))],
            summary="Create new shift assignment",
            description="Create a new shift assignment for a user.")
async def create_shift_assignment_endpoint(
    shift_assignment: ShiftAssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> ShiftAssignmentOut:
    """
    Create a shift assignment by delegating to shift_pattern_service.
    """
    return await service_create_shift_assignment(shift_assignment, db, current_user, settings)

@router.get("/{assignment_id}", 
            response_model=ShiftAssignmentOut,
            summary="Get shift assignment by ID",
            description="Retrieve a shift assignment by its ID.")
async def read_shift_assignment_endpoint(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> ShiftAssignmentOut:
    """
    Retrieve a shift assignment by ID by delegating to shift_pattern_service.
    """
    return await service_read_shift_assignment(assignment_id, current_user, db, settings)

@router.get("/", 
            response_model=List[ShiftAssignmentOut],
            summary="List shift assignments",
            description="List shift assignments, optionally filtered by user ID.")
async def read_shift_assignments_endpoint(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> List[ShiftAssignmentOut]:
    """
    List shift assignments by delegating to shift_pattern_service.
    """
    return await service_read_shift_assignments(user_id, skip, limit, current_user, db, settings)

@router.put("/{assignment_id}", 
            response_model=ShiftAssignmentOut,
            dependencies=[Depends(require_permissions([Permission.MANAGE_USERS]))],
            summary="Update shift assignment",
            description="Update an existing shift assignment.")
async def update_shift_assignment_endpoint(
    assignment_id: int,
    shift_assignment_update: ShiftAssignmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> ShiftAssignmentOut:
    """
    Update a shift assignment by delegating to shift_pattern_service.
    """
    return await service_update_shift_assignment(assignment_id, shift_assignment_update, current_user, db, settings)

@router.delete("/{assignment_id}", 
            status_code=status.HTTP_204_NO_CONTENT,
            dependencies=[Depends(require_permissions([Permission.MANAGE_USERS]))],
            summary="Delete shift assignment",
            description="Soft delete a shift assignment.")
async def delete_shift_assignment_endpoint(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> None:
    """
    Soft delete a shift assignment by delegating to shift_pattern_service.
    """
    await service_delete_shift_assignment(assignment_id, current_user, db, settings)

@router.get("/my-shifts", 
            response_model=List[ShiftAssignmentOut],
            dependencies=[Depends(require_permissions([Permission.VIEW_OWN_ATTENDANCE]))],
            summary="Get current user's shift assignments",
            description="Retrieve the current user's shift assignments.")
async def get_my_shift_assignments_endpoint(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> List[ShiftAssignmentOut]:
    """
    Retrieve the current user's shift assignments by delegating to shift_pattern_service.
    """
    return await service_get_my_shift_assignments(skip, limit, current_user, db, settings)