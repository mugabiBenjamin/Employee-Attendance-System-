from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, cast
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.enums import CorrectionStatus, Permission
from app.core.config import Settings, get_settings
from app.core.utils import get_request_id
from app.services.time_correction_service import (
    create_time_correction as service_create_time_correction,
    get_time_correction as service_get_time_correction,
    get_user_time_corrections as service_get_user_time_corrections,
    get_department_time_corrections as service_get_department_time_corrections,
    update_time_correction as service_update_time_correction,
    approve_time_correction as service_approve_time_correction,
    delete_time_correction as service_delete_time_correction
)
from app.schemas.time_correction import TimeCorrectionCreate, TimeCorrectionUpdate, TimeCorrectionOut, TimeCorrectionApproval
from app.core.exceptions import ValidationError
from app.core.permissions import require_permissions_dependency, require_any_permissions_dependency

router = APIRouter(prefix="/time-corrections", tags=["Time Corrections"])

@router.post(
    "/",
    response_model=TimeCorrectionOut,
    status_code=201,
    summary="Request a time correction"
)
async def request_time_correction(
    correction: TimeCorrectionCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.CREATE_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """Submit a time correction request for an attendance record."""
    request_id = get_request_id(request)
    return await service_create_time_correction(correction, request, current_user, db, settings, request_id)

@router.get(
    "/{correction_id}",
    response_model=TimeCorrectionOut,
    summary="Get time correction by ID"
)
async def get_time_correction(
    correction_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_permissions_dependency([Permission.VIEW_TIME_CORRECTION, Permission.MANAGE_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """Retrieve a specific time correction request."""
    request_id = get_request_id(request)
    return await service_get_time_correction(correction_id, current_user, db, request_id)

@router.get(
    "/",
    response_model=List[TimeCorrectionOut],
    summary="List time correction requests"
)
async def list_time_corrections(
    request: Request,
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    status: Optional[CorrectionStatus] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_any_permissions_dependency([Permission.VIEW_TIME_CORRECTION, Permission.MANAGE_TIME_CORRECTION]))
) -> List[TimeCorrectionOut]:
    """Retrieve time correction requests for current user, specified user, or department."""
    request_id = get_request_id(request)
    if department_id:
        return await service_get_department_time_corrections(department_id, skip, limit, status, current_user, db, settings, request_id)
    
    target_user_id = user_id if user_id else cast(int, current_user.user_id)
    return await service_get_user_time_corrections(target_user_id, skip, limit, status, current_user, db, settings, request_id)

@router.put(
    "/{correction_id}",
    response_model=TimeCorrectionOut,
    summary="Update a time correction"
)
async def update_time_correction(
    correction_id: int,
    time_correction_update: TimeCorrectionUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.UPDATE_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """Update an existing time correction request."""
    request_id = get_request_id(request)
    return await service_update_time_correction(correction_id, time_correction_update, request, current_user, db, settings, request_id)

@router.put(
    "/{correction_id}/approve",
    response_model=TimeCorrectionOut,
    summary="Approve or reject a time correction"
)
async def approve_reject_time_correction(
    correction_id: int,
    approval_data: TimeCorrectionApproval,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.MANAGE_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """Approve or reject a time correction request."""
    request_id = get_request_id(request)
    return await service_approve_time_correction(correction_id, approval_data, request, current_user, db, settings, request_id)

@router.delete(
    "/{correction_id}",
    status_code=204,
    summary="Delete a time correction"
)
async def remove_time_correction(
    correction_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.DELETE_TIME_CORRECTION]))
) -> None:
    """Soft delete a time correction request (HR/admin only)."""
    request_id = get_request_id(request)
    await service_delete_time_correction(correction_id, request, current_user, db, settings, request_id)