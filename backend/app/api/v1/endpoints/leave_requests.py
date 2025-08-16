from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.leave_request_service import (
    create_leave_request as service_create_leave_request,
    get_leave_requests as service_get_leave_requests,
    approve_reject_leave_request as service_approve_reject_leave_request
)
from app.schemas.leave_request import LeaveRequestCreate, LeaveRequestOut, LeaveApprovalUpdate
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leave-requests", tags=["Leave Requests"])

@router.post("/", 
             response_model=LeaveRequestOut, 
             status_code=status.HTTP_201_CREATED,
             summary="Create leave request",
             description="Create a new leave request.")
@require_permissions([Permission.REQUEST_LEAVE])
async def create_leave_request_endpoint(
    request: Request,
    leave_request: LeaveRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> LeaveRequestOut:
    """
    Create a leave request by delegating to leave_request_service.
    """
    return await service_create_leave_request(leave_request, current_user, db, settings)

@router.get("/history", 
            response_model=List[LeaveRequestOut],
            summary="Get leave request history",
            description="Retrieve leave request history for the current user or team (if authorized).")
@require_permissions([Permission.REQUEST_LEAVE, Permission.VIEW_ALL_ATTENDANCE])
async def get_leave_requests_endpoint(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> List[LeaveRequestOut]:
    """
    Retrieve leave request history by delegating to leave_request_service.
    """
    return await service_get_leave_requests(user_id, skip, limit, current_user, db, settings)

@router.put("/approve/{leave_id}", 
            response_model=LeaveRequestOut,
            summary="Approve/reject leave request",
            description="Approve or reject a leave request.")
@require_permissions([Permission.APPROVE_LEAVE])
async def approve_reject_leave_request_endpoint(
    leave_id: int,
    approval: LeaveApprovalUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> LeaveRequestOut:
    """
    Approve or reject a leave request by delegating to leave_request_service.
    """
    return await service_approve_reject_leave_request(leave_id, approval, current_user, db, settings)