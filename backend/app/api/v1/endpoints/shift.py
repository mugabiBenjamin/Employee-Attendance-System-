from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.user import (
    ShiftPatternCreate, ShiftPatternUpdate, ShiftPatternOut,
    ShiftAssignmentCreate, ShiftAssignmentUpdate, ShiftAssignmentOut
)
from app.services.shift_service import (
    create_shift_pattern, get_shift_pattern_by_id, get_shift_patterns,
    update_shift_pattern, delete_shift_pattern,
    create_shift_assignment, get_shift_assignment_by_id,
    get_shift_assignments, update_shift_assignment, delete_shift_assignment
)
from app.api.deps import get_db_session, get_current_active_user
from app.services.auth_service import check_user_permission
from app.models.user import User
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

async def is_admin_or_manager(db: AsyncSession, user: User) -> bool:
    from sqlmodel import select
    from app.models.user_roles import UserRoles
    query = select(UserRoles).join(UserRoles).where(
        UserRoles.user_id == user.user_id,
        UserRoles.is_active == True,
        UserRoles.role_name.in_(["Manager", "HR", "Admin", "Super_Admin"])
    )
    result = await db.execute(query)
    return result.first() is not None

@router.post("/pattern", 
    response_model=ShiftPatternOut, 
    status_code=status.HTTP_201_CREATED,
    summary="Create new shift pattern",
    description="Create a new shift pattern. Requires manage_shifts permission."
)
async def create_new_shift_pattern(
    shift_pattern: ShiftPatternCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new shift pattern in the system."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_shifts")
    if not has_permission and not await is_admin_or_manager(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to create shift patterns")
    
    valid_shift_types = ["morning", "afternoon", "night", "flexible", "split"]
    if shift_pattern.shift_type not in valid_shift_types:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                          detail=f"Invalid shift type. Must be one of {valid_shift_types}")
    
    return await create_shift_pattern(db, shift_pattern, current_user)

@router.get("/pattern/{pattern_id}", 
    response_model=ShiftPatternOut,
    summary="Get shift pattern by ID",
    description="Retrieve shift pattern details. Requires view_shifts permission or manager/admin access."
)
async def read_shift_pattern(
    pattern_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific shift pattern by its ID."""
    has_permission = await check_user_permission(db, current_user.user_id, "view_shifts")
    if not has_permission and not await is_admin_or_manager(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to view shift patterns")
    
    shift_pattern = await get_shift_pattern_by_id(db, pattern_id)
    if not shift_pattern:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                          detail="Shift pattern not found")
    
    return shift_pattern

@router.get("/patterns", 
    response_model=List[ShiftPatternOut],
    summary="List all shift patterns",
    description="Retrieve all shift patterns with pagination. Requires view_shifts permission or manager/admin access."
)
async def read_shift_patterns(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get a paginated list of all shift patterns."""
    has_permission = await check_user_permission(db, current_user.user_id, "view_shifts")
    if not has_permission and not await is_admin_or_manager(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to view shift patterns")
    
    return await get_shift_patterns(db, skip, limit)

@router.put("/pattern/{pattern_id}", 
    response_model=ShiftPatternOut,
    summary="Update shift pattern",
    description="Update shift pattern information. Requires manage_shifts permission."
)
async def update_existing_shift_pattern(
    pattern_id: int,
    shift_update: ShiftPatternUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Update an existing shift pattern's information."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_shifts")
    if not has_permission and not await is_admin_or_manager(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to update shift patterns")
    
    if shift_update.shift_type:
        valid_shift_types = ["morning", "afternoon", "night", "flexible", "split"]
        if shift_update.shift_type not in valid_shift_types:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"Invalid shift type. Must be one of {valid_shift_types}")
    
    return await update_shift_pattern(db, pattern_id, shift_update, current_user)

@router.delete("/pattern/{pattern_id}", 
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete shift pattern",
    description="Delete a shift pattern. Requires manage_shifts permission."
)
async def delete_existing_shift_pattern(
    pattern_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a shift pattern from the system."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_shifts")
    if not has_permission and not await is_admin_or_manager(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to delete shift patterns")
    
    await delete_shift_pattern(db, pattern_id)
    return None

@router.post("/assignment", 
    response_model=ShiftAssignmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create new shift assignment",
    description="Assign a shift pattern to a user. Requires manage_shifts permission."
)
async def create_new_shift_assignment(
    shift_assignment: ShiftAssignmentCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new shift assignment."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_shifts")
    if not has_permission and not await is_admin_or_manager(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to create shift assignments")
    
    return await create_shift_assignment(db, shift_assignment, current_user)

@router.get("/assignment/{assignment_id}", 
    response_model=ShiftAssignmentOut,
    summary="Get shift assignment by ID",
    description="Retrieve shift assignment details. Requires view_shifts permission or manager/admin access."
)
async def read_shift_assignment(
    assignment_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific shift assignment by its ID."""
    has_permission = await check_user_permission(db, current_user.user_id, "view_shifts")
    if not has_permission and not await is_admin_or_manager(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to view shift assignments")
    
    assignment = await get_shift_assignment_by_id(db, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                          detail="Shift assignment not found")
    
    return assignment

@router.get("/assignments", 
    response_model=List[ShiftAssignmentOut],
    summary="List shift assignments",
    description="Retrieve shift assignments for a user or all users with pagination. Requires view_shifts permission or manager/admin access."
)
async def read_shift_assignments(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get a paginated list of shift assignments."""
    has_permission = await check_user_permission(db, current_user.user_id, "view_shifts")
    if user_id and user_id != current_user.user_id and not has_permission and not await is_admin_or_manager(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to view other users' shift assignments")
    
    return await get_shift_assignments(db, user_id, skip, limit)

@router.put("/assignment/{assignment_id}", 
    response_model=ShiftAssignmentOut,
    summary="Update shift assignment",
    description="Update shift assignment information. Requires manage_shifts permission."
)
async def update_existing_shift_assignment(
    assignment_id: int,
    shift_update: ShiftAssignmentUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Update an existing shift assignment's information."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_shifts")
    if not has_permission and not await is_admin_or_manager(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to update shift assignments")
    
    return await update_shift_assignment(db, assignment_id, shift_update, current_user)

@router.delete("/assignment/{assignment_id}", 
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete shift assignment",
    description="Delete a shift assignment. Requires manage_shifts permission."
)
async def delete_existing_shift_assignment(
    assignment_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a shift assignment from the system."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_shifts")
    if not has_permission and not await is_admin_or_manager(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to delete shift assignments")
    
    await delete_shift_assignment(db, assignment_id)
    return None