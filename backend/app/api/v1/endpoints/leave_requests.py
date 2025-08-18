from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.leave_request_service import (
    create_leave_request,
    get_leave_request,
    get_leave_requests,
    approve_reject_leave_request
)
from app.schemas.leave_request import LeaveRequestCreate, LeaveRequestOut, LeaveApprovalUpdate
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leave-requests", tags=["Leave Requests"])

@router.post(
    "/",
    response_model=LeaveRequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create leave request",
    description="Create a new leave request with validation and notification."
)
@require_permissions([Permission.CREATE_LEAVE_REQUEST])
async def create_leave_request_endpoint(
    leave_request: LeaveRequestCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> LeaveRequestOut:
    """Create a new leave request.

    Args:
        leave_request: Leave request creation data.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        LeaveRequestOut: The created leave request.
    """
    return await create_leave_request(leave_request, request, current_user, db)

@router.get(
    "/{request_id}",
    response_model=LeaveRequestOut,
    summary="Get leave request by ID",
    description="Retrieve a leave request by ID for the current user or their subordinates."
)
@require_permissions([Permission.VIEW_LEAVE_REQUEST, Permission.VIEW_OWN_LEAVE_REQUEST])
async def get_leave_request_endpoint(
    request_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> LeaveRequestOut:
    """Retrieve a leave request by ID.

    Args:
        request_id: The ID of the leave request to retrieve.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        LeaveRequestOut: The retrieved leave request.
    """
    return await get_leave_request(request_id, current_user, db)

@router.get(
    "/",
    response_model=List[LeaveRequestOut],
    summary="List leave requests",
    description="Retrieve a list of leave requests for the current user or their subordinates with pagination."
)
@require_permissions([Permission.VIEW_LEAVE_REQUEST, Permission.VIEW_OWN_LEAVE_REQUEST])
async def get_leave_requests_endpoint(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[LeaveRequestOut]:
    """List leave requests with pagination.

    Args:
        user_id: Optional user ID to filter leave requests.
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return.
        current_user: The authenticated user.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[LeaveRequestOut]: List of leave requests.
    """
    return await get_leave_requests(user_id, skip, limit, current_user, db, settings)

@router.put(
    "/{leave_id}",
    response_model=LeaveRequestOut,
    summary="Approve or reject leave request",
    description="Approve or reject a leave request with balance update and notification."
)
@require_permissions([Permission.APPROVE_LEAVE])
async def approve_reject_leave_request_endpoint(
    leave_id: int,
    approval: LeaveApprovalUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> LeaveRequestOut:
    """Approve or reject a leave request.

    Args:
        leave_id: The ID of the leave request to approve/reject.
        approval: Approval data containing status and comments.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        LeaveRequestOut: The updated leave request.
    """
    return await approve_reject_leave_request(leave_id, approval, request, current_user, db)