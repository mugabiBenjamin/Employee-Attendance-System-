from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import date
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import LeaveRequestStatus, LeaveType, Permission
from app.core.permissions import require_permissions_dependency
from app.core.utils import get_request_id
from app.services.leave_request_service import (
    create_leave_request,
    get_leave_request,
    get_leave_requests,
    get_team_leave_requests,
    update_leave_request,
    approve_reject_leave_request,
    delete_leave_request
)
from app.schemas.leave_request import LeaveRequestCreate, LeaveRequestUpdate, LeaveRequestOut, LeaveApprovalUpdate

router = APIRouter(prefix="/leave-requests", tags=["Leave Requests"])

@router.post(
    "/",
    response_model=LeaveRequestOut,
    status_code=201,
    summary="Create a leave request"
)
async def create_leave_request_endpoint(
    leave_request: LeaveRequestCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.CREATE_LEAVE_REQUEST]))
) -> LeaveRequestOut:
    """Create a new leave request."""
    request_id = get_request_id(request)
    return await create_leave_request(leave_request, request, current_user, db, settings, request_id)

@router.get(
    "/{leave_id}",
    response_model=LeaveRequestOut,
    summary="Get leave request by ID"
)
async def get_leave_request_endpoint(
    leave_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_LEAVE_REQUEST, Permission.VIEW_OWN_LEAVE_REQUEST]))
) -> LeaveRequestOut:
    """Retrieve a leave request by ID."""
    request_id = get_request_id(request)
    return await get_leave_request(leave_id, current_user, db, settings, request_id)

@router.get(
    "/",
    response_model=List[LeaveRequestOut],
    summary="List leave requests"
)
async def get_leave_requests_endpoint(
    request: Request,
    user_id: Optional[int] = None,
    status: Optional[LeaveRequestStatus] = None,
    leave_type: Optional[LeaveType] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_LEAVE_REQUEST, Permission.VIEW_OWN_LEAVE_REQUEST]))
) -> List[LeaveRequestOut]:
    """List leave requests with pagination and optional filters."""
    request_id = get_request_id(request)
    return await get_leave_requests(user_id, status, leave_type, skip, limit, current_user, db, settings, request_id)

@router.get(
    "/team",
    response_model=List[LeaveRequestOut],
    summary="List team leave requests"
)
async def get_team_leave_requests_endpoint(
    request: Request,
    status: Optional[LeaveRequestStatus] = None,
    leave_type: Optional[LeaveType] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_TEAM_LEAVE_REQUESTS]))
) -> List[LeaveRequestOut]:
    """List leave requests for a manager's team."""
    request_id = get_request_id(request)
    return await get_team_leave_requests(status, leave_type, start_date, end_date, skip, limit, current_user, db, settings, request_id)

@router.put(
    "/{leave_id}",
    response_model=LeaveRequestOut,
    summary="Update a leave request"
)
async def update_leave_request_endpoint(
    leave_id: int,
    leave_request_update: LeaveRequestUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.UPDATE_LEAVE_REQUEST]))
) -> LeaveRequestOut:
    """Update a leave request."""
    request_id = get_request_id(request)
    return await update_leave_request(leave_id, leave_request_update, request, current_user, db, settings, request_id)

@router.put(
    "/{leave_id}/approve",
    response_model=LeaveRequestOut,
    summary="Approve or reject a leave request"
)
async def approve_reject_leave_request_endpoint(
    leave_id: int,
    approval: LeaveApprovalUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.APPROVE_LEAVE]))
) -> LeaveRequestOut:
    """Approve or reject a leave request."""
    request_id = get_request_id(request)
    return await approve_reject_leave_request(leave_id, approval, request, current_user, db, settings, request_id)

@router.delete(
    "/{leave_id}",
    status_code=204,
    summary="Delete a leave request"
)
async def delete_leave_request_endpoint(
    leave_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.DELETE_LEAVE_REQUEST]))
) -> None:
    """Soft delete a leave request."""
    request_id = get_request_id(request)
    await delete_leave_request(leave_id, request, current_user, db, settings, request_id)