from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import LeaveType, Permission
from app.core.utils import get_request_id
from app.core.permissions import require_permissions_dependency
from app.services.leave_approval_workflow_service import (
    approve_or_reject_leave,
    get_leave_approval,
    get_leave_approvals_by_request,
    update_leave_approval,
    delete_leave_approval,
    define_workflow_steps,
    get_workflow_by_type
)
from app.schemas.leave_approval_workflow import (
    LeaveApprovalWorkflowCreate,
    LeaveApprovalWorkflowUpdate,
    LeaveApprovalWorkflowOut,
    WorkflowStepCreate,
    WorkflowStepOut
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leave-approval-workflow", tags=["Leave Approval Workflow"])

@router.post(
    "/approve",
    response_model=LeaveApprovalWorkflowOut,
    status_code=status.HTTP_201_CREATED,
    summary="Approve or reject a leave request",
    description="Approve or reject a leave request with validation and notifications."
)
async def approve_leave_endpoint(
    approval: LeaveApprovalWorkflowCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.APPROVE_LEAVE]))
) -> LeaveApprovalWorkflowOut:
    """Approve or reject a leave request with workflow validation."""
    request_id = get_request_id(request)
    return await approve_or_reject_leave(approval, request, current_user, db, settings, request_id)

@router.get(
    "/{workflow_id}",
    response_model=LeaveApprovalWorkflowOut,
    summary="Get leave approval by ID",
    description="Retrieve a specific leave approval workflow entry by its ID."
)
async def get_leave_approval_endpoint(
    workflow_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_LEAVE_APPROVAL]))
) -> LeaveApprovalWorkflowOut:
    """Retrieve a leave approval by ID."""
    request_id = get_request_id(request)
    return await get_leave_approval(workflow_id, current_user, db, settings, request_id)

@router.get(
    "/request/{leave_id}",
    response_model=List[LeaveApprovalWorkflowOut],
    summary="List leave approvals by request",
    description="Retrieve a list of approvals for a specific leave request with pagination."
)
async def get_leave_approvals_by_request_endpoint(
    request: Request,
    leave_id: int,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_LEAVE_APPROVAL]))
) -> List[LeaveApprovalWorkflowOut]:
    """List leave approvals for a leave request with pagination."""
    request_id = get_request_id(request)
    return await get_leave_approvals_by_request(leave_id, skip, limit, current_user, db, settings, request_id)

@router.put(
    "/{workflow_id}",
    response_model=LeaveApprovalWorkflowOut,
    summary="Update leave approval",
    description="Update a leave approval workflow entry with validation and notifications."
)
async def update_leave_approval_endpoint(
    workflow_id: int,
    update_data: LeaveApprovalWorkflowUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.MANAGE_LEAVE]))
) -> LeaveApprovalWorkflowOut:
    """Update a leave approval workflow entry."""
    request_id = get_request_id(request)
    return await update_leave_approval(workflow_id, update_data, request, current_user, db, settings, request_id)

@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete leave approval",
    description="Soft delete a leave approval workflow entry with validation and notifications."
)
async def delete_leave_approval_endpoint(
    workflow_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.MANAGE_LEAVE]))
) -> None:
    """Soft delete a leave approval workflow entry."""
    request_id = get_request_id(request)
    await delete_leave_approval(workflow_id, request, current_user, db, settings, request_id)

@router.post(
    "/steps",
    response_model=List[WorkflowStepOut],
    status_code=status.HTTP_201_CREATED,
    summary="Define leave approval workflow steps",
    description="Define steps for a leave approval workflow with approver sequencing and notifications."
)
async def define_workflow_steps_endpoint(
    workflow_steps: List[WorkflowStepCreate],
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.MANAGE_WORKFLOWS]))
) -> List[WorkflowStepOut]:
    """Define leave approval workflow steps."""
    request_id = get_request_id(request)
    return await define_workflow_steps(workflow_steps, request, current_user, db, settings, request_id)

@router.get(
    "/type/{leave_type}",
    response_model=List[WorkflowStepOut],
    summary="Get workflow by leave type",
    description="Retrieve approval workflow steps for a specific leave type with pagination."
)
async def get_workflow_by_type_endpoint(
    leave_type: LeaveType,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_WORKFLOWS]))
) -> List[WorkflowStepOut]:
    """Retrieve workflow steps by leave type."""
    request_id = get_request_id(request)
    return await get_workflow_by_type(leave_type, current_user, db, settings, request_id)