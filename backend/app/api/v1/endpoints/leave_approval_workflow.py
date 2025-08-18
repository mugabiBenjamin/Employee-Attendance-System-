from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.leave_approval_workflow_service import (
    approve_or_reject_leave,
    get_leave_approval,
    get_leave_approvals_by_request,
    define_workflow_steps,
    get_workflow_by_type
)
from app.schemas.leave_approval_workflow import (
    LeaveApprovalWorkflowCreate,
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
    description="Approve or reject a leave request with validation and notification."
)
@require_permissions([Permission.APPROVE_LEAVE])
async def approve_leave_endpoint(
    approval: LeaveApprovalWorkflowCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> LeaveApprovalWorkflowOut:
    """Approve or reject a leave request.

    Args:
        approval: Approval workflow creation data.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        LeaveApprovalWorkflowOut: The created approval workflow entry.
    """
    return await approve_or_reject_leave(approval, request, current_user, db)

@router.get(
    "/{approval_id}",
    response_model=LeaveApprovalWorkflowOut,
    summary="Get leave approval by ID",
    description="Retrieve a leave approval by its ID."
)
@require_permissions([Permission.VIEW_LEAVE_APPROVAL])
async def get_leave_approval_endpoint(
    approval_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> LeaveApprovalWorkflowOut:
    """Retrieve a leave approval by ID.

    Args:
        approval_id: The ID of the approval workflow to retrieve.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        LeaveApprovalWorkflowOut: The retrieved approval workflow.
    """
    return await get_leave_approval(approval_id, current_user, db)

@router.get(
    "/request/{request_id}",
    response_model=List[LeaveApprovalWorkflowOut],
    summary="List leave approvals by request",
    description="Retrieve a list of approvals for a leave request with pagination."
)
@require_permissions([Permission.VIEW_LEAVE_APPROVAL])
async def get_leave_approvals_by_request_endpoint(
    request_id: int,
    skip: int = 0,
    limit: int = 50,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[LeaveApprovalWorkflowOut]:
    """List leave approvals for a leave request with pagination.

    Args:
        request_id: The ID of the leave request.
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return.
        current_user: The authenticated user.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[LeaveApprovalWorkflowOut]: List of approval workflows.
    """
    return await get_leave_approvals_by_request(request_id, skip, limit, current_user, db, settings)

@router.post(
    "/steps",
    response_model=List[WorkflowStepOut],
    status_code=status.HTTP_201_CREATED,
    summary="Define leave approval workflow steps",
    description="Define steps for a leave approval workflow with approver sequencing."
)
@require_permissions([Permission.MANAGE_WORKFLOWS])
async def define_workflow_steps_endpoint(
    workflow_steps: List[WorkflowStepCreate],
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[WorkflowStepOut]:
    """Define leave approval workflow steps.

    Args:
        workflow_steps: List of workflow step creation data.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[WorkflowStepOut]: List of created workflow steps.
    """
    return await define_workflow_steps(workflow_steps, current_user, db, settings)

@router.get(
    "/type/{leave_type}",
    response_model=List[WorkflowStepOut],
    summary="Get workflow by leave type",
    description="Retrieve approval workflow steps for a specific leave type."
)
@require_permissions([Permission.VIEW_WORKFLOWS])
async def get_workflow_by_type_endpoint(
    leave_type: str,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[WorkflowStepOut]:
    """Retrieve workflow steps by leave type.

    Args:
        leave_type: The type of leave to filter workflows.
        current_user: The authenticated user.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[WorkflowStepOut]: List of workflow steps.
    """
    return await get_workflow_by_type(leave_type, current_user, db, settings)