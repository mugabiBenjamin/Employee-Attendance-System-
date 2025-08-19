from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.core.exceptions import ValidationError
from app.services.leave_request_service import (
    create_leave_request,
    get_leave_request,
    get_leave_requests,
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
    summary="Create leave request",
    description="Create a new leave request with validation and notification."
)
@require_permissions([Permission.CREATE_LEAVE_REQUEST])
async def create_leave_request_endpoint(
    leave_request: LeaveRequestCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> LeaveRequestOut:
    """Create a new leave request."""
    try:
        request_id = getattr(request.state, "request_id", None)
        return await create_leave_request(leave_request, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error creating leave request: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating leave request: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating leave request")

@router.get(
    "/{leave_id}",
    response_model=LeaveRequestOut,
    summary="Get leave request by ID",
    description="Retrieve a leave request by ID for the current user or their subordinates."
)
@require_permissions([Permission.VIEW_LEAVE_REQUEST, Permission.VIEW_OWN_LEAVE_REQUEST])
async def get_leave_request_endpoint(
    leave_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> LeaveRequestOut:
    """Retrieve a leave request by ID."""
    try:
        if leave_id <= 0:
            raise ValidationError(detail="Invalid leave_id")
        request_id = getattr(request.state, "request_id", None)
        return await get_leave_request(leave_id, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error retrieving leave request {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave request {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave request")

@router.get(
    "/",
    response_model=List[LeaveRequestOut],
    summary="List leave requests",
    description="Retrieve a list of leave requests for the current user or their subordinates with pagination."
)
@require_permissions([Permission.VIEW_LEAVE_REQUEST, Permission.VIEW_OWN_LEAVE_REQUEST])
async def get_leave_requests_endpoint(
    request: Request,
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[LeaveRequestOut]:
    """List leave requests with pagination."""
    try:
        if user_id is not None and user_id <= 0:
            raise ValidationError(detail="Invalid user_id")
        request_id = getattr(request.state, "request_id", None)
        return await get_leave_requests(user_id, skip, limit, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error retrieving leave requests: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave requests: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave requests")

@router.put(
    "/{leave_id}",
    response_model=LeaveRequestOut,
    summary="Update leave request",
    description="Update an existing leave request with validation and notification."
)
@require_permissions([Permission.UPDATE_LEAVE_REQUEST])
async def update_leave_request_endpoint(
    leave_id: int,
    leave_request_update: LeaveRequestUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> LeaveRequestOut:
    """Update a leave request."""
    try:
        if leave_id <= 0:
            raise ValidationError(detail="Invalid leave_id")
        request_id = getattr(request.state, "request_id", None)
        return await update_leave_request(leave_id, leave_request_update, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error updating leave request {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating leave request {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating leave request")

@router.put(
    "/{leave_id}/approve",
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
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> LeaveRequestOut:
    """Approve or reject a leave request."""
    try:
        if leave_id <= 0:
            raise ValidationError(detail="Invalid leave_id")
        request_id = getattr(request.state, "request_id", None)
        return await approve_reject_leave_request(leave_id, approval, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error approving leave request {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error approving leave request {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing leave request")

@router.delete(
    "/{leave_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete leave request",
    description="Soft delete a leave request with validation and notification."
)
@require_permissions([Permission.DELETE_LEAVE_REQUEST])
async def delete_leave_request_endpoint(
    leave_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> None:
    """Soft delete a leave request."""
    try:
        if leave_id <= 0:
            raise ValidationError(detail="Invalid leave_id")
        request_id = getattr(request.state, "request_id", None)
        await delete_leave_request(leave_id, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error deleting leave request {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting leave request {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting leave request")