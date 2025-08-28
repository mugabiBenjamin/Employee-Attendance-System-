from fastapi import APIRouter, Depends, HTTPException, status, Request
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
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leave-requests", tags=["Leave Requests"])

@router.post(
    "/",
    response_model=LeaveRequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a leave request",
    description="Create a new leave request with validation and notifications."
)
async def create_leave_request_endpoint(
    leave_request: LeaveRequestCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.CREATE_LEAVE_REQUEST]))
) -> LeaveRequestOut:
    """Create a new leave request.

    Args:
        leave_request: The leave request data to create.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        LeaveRequestOut: The created leave request.

    Raises:
        HTTPException: For validation errors (422), not found (404), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await create_leave_request(leave_request, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error creating leave request: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating leave request: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/{leave_id}",
    response_model=LeaveRequestOut,
    summary="Get leave request by ID",
    description="Retrieve a specific leave request by its ID."
)
async def get_leave_request_endpoint(
    leave_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_LEAVE_REQUEST, Permission.VIEW_OWN_LEAVE_REQUEST]))
) -> LeaveRequestOut:
    """Retrieve a leave request by ID.

    Args:
        leave_id: The ID of the leave request to retrieve.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        LeaveRequestOut: The retrieved leave request.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await get_leave_request(leave_id, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving leave request {leave_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave request {leave_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/",
    response_model=List[LeaveRequestOut],
    summary="List leave requests",
    description="List leave requests with optional filters and pagination."
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
    """List leave requests with pagination and optional filters.

    Args:
        user_id: Optional user ID to filter leave requests.
        status: Optional filter for leave request status (e.g., UNDER_REVIEW, APPROVED, REJECTED).
        leave_type: Optional filter for leave type (e.g., ANNUAL, SICK).
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: DEFAULT_PAGE_SIZE).
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[LeaveRequestOut]: List of leave requests.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await get_leave_requests(user_id, status, leave_type, skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving leave requests: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave requests: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/team",
    response_model=List[LeaveRequestOut],
    summary="List team leave requests",
    description="List leave requests for a manager's team with optional filters and pagination."
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
    """List leave requests for a manager's team.

    Args:
        status: Optional filter for leave request status (e.g., UNDER_REVIEW, APPROVED, REJECTED).
        leave_type: Optional filter for leave type (e.g., ANNUAL, SICK).
        start_date: Optional start date for filtering records.
        end_date: Optional end date for filtering records.
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: DEFAULT_PAGE_SIZE).
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[LeaveRequestOut]: List of leave requests for the manager's team.

    Raises:
        HTTPException: For validation errors (422), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await get_team_leave_requests(status, leave_type, start_date, end_date, skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving team leave requests: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving team leave requests: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{leave_id}",
    response_model=LeaveRequestOut,
    summary="Update a leave request",
    description="Update an existing leave request with new details."
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
    """Update a leave request.

    Args:
        leave_id: The ID of the leave request to update.
        leave_request_update: The updated leave request data.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        LeaveRequestOut: The updated leave request.

    Raises:
        HTTPException: For validation errors (422), not found (404), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await update_leave_request(leave_id, leave_request_update, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error updating leave request {leave_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating leave request {leave_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{leave_id}/approve",
    response_model=LeaveRequestOut,
    summary="Approve or reject a leave request",
    description="Approve or reject a leave request with balance update and notifications."
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
    """Approve or reject a leave request.

    Args:
        leave_id: The ID of the leave request to approve or reject.
        approval: The approval data including status and comments.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        LeaveRequestOut: The updated leave request.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await approve_reject_leave_request(leave_id, approval, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error approving leave request {leave_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error approving leave request {leave_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{leave_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a leave request",
    description="Soft delete a leave request with notifications."
)
async def delete_leave_request_endpoint(
    leave_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.DELETE_LEAVE_REQUEST]))
) -> None:
    """Soft delete a leave request.

    Args:
        leave_id: The ID of the leave request to delete.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        None: No content returned on successful deletion.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), business logic errors (422), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        await delete_leave_request(leave_id, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error deleting leave request {leave_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting leave request {leave_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")