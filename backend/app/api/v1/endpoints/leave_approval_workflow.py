from fastapi import APIRouter, Depends, status, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission, LeaveType
from app.core.exceptions import ValidationError
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
    WorkflowStepOut,
    WorkflowByTypeQuery
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
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> LeaveApprovalWorkflowOut:
    """Approve or reject a leave request."""
    try:
        if approval.leave_id <= 0 or approval.approver_id <= 0:
            raise ValidationError(detail="Invalid leave_id or approver_id")
        request_id = getattr(request.state, "request_id", None)
        return await approve_or_reject_leave(approval, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error approving leave: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error approving leave: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/{workflow_id}",
    response_model=LeaveApprovalWorkflowOut,
    summary="Get leave approval by ID",
    description="Retrieve a leave approval by its ID."
)
@require_permissions([Permission.VIEW_LEAVE_APPROVAL])
async def get_leave_approval_endpoint(
    workflow_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> LeaveApprovalWorkflowOut:
    """Retrieve a leave approval by ID."""
    try:
        if workflow_id <= 0:
            raise ValidationError(detail="Invalid workflow_id")
        request_id = getattr(request.state, "request_id", None)
        return await get_leave_approval(workflow_id, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error retrieving leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/request/{leave_id}",
    response_model=List[LeaveApprovalWorkflowOut],
    summary="List leave approvals by request",
    description="Retrieve a list of approvals for a leave request with pagination."
)
@require_permissions([Permission.VIEW_LEAVE_APPROVAL])
async def get_leave_approvals_by_request_endpoint(
    request: Request,
    leave_id: int,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[LeaveApprovalWorkflowOut]:
    """List leave approvals for a leave request with pagination."""
    try:
        if leave_id <= 0:
            raise ValidationError(detail="Invalid leave_id")
        request_id = getattr(request.state, "request_id", None)
        return await get_leave_approvals_by_request(leave_id, skip, limit, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error retrieving leave approvals for leave_id {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave approvals for leave_id {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{workflow_id}",
    response_model=LeaveApprovalWorkflowOut,
    summary="Update leave approval",
    description="Update a leave approval workflow entry with validation and notification."
)
@require_permissions([Permission.MANAGE_LEAVE])
async def update_leave_approval_endpoint(
    workflow_id: int,
    update_data: LeaveApprovalWorkflowUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> LeaveApprovalWorkflowOut:
    """Update a leave approval."""
    try:
        if workflow_id <= 0:
            raise ValidationError(detail="Invalid workflow_id")
        request_id = getattr(request.state, "request_id", None)
        return await update_leave_approval(workflow_id, update_data, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error updating leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete leave approval",
    description="Soft delete a leave approval workflow entry with validation and notification."
)
@require_permissions([Permission.MANAGE_LEAVE])
async def delete_leave_approval_endpoint(
    workflow_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> None:
    """Soft delete a leave approval."""
    try:
        if workflow_id <= 0:
            raise ValidationError(detail="Invalid workflow_id")
        request_id = getattr(request.state, "request_id", None)
        await delete_leave_approval(workflow_id, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error deleting leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

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
    """Define leave approval workflow steps."""
    try:
        for step in workflow_steps:
            if step.leave_id <= 0 or step.approver_id <= 0:
                raise ValidationError(detail="Invalid leave_id or approver_id")
        request_id = getattr(request.state, "request_id", None)
        return await define_workflow_steps(workflow_steps, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error defining workflow steps: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error defining workflow steps: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/type/{leave_type}",
    response_model=List[WorkflowStepOut],
    summary="Get workflow by leave type",
    description="Retrieve approval workflow steps for a specific leave type."
)
@require_permissions([Permission.VIEW_WORKFLOWS])
async def get_workflow_by_type_endpoint(
    leave_type: LeaveType,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[WorkflowStepOut]:
    """Retrieve workflow steps by leave type."""
    try:
        request_id = getattr(request.state, "request_id", None)
        return await get_workflow_by_type(leave_type, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error retrieving workflow steps for leave_type {leave_type}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving workflow steps for leave_type {leave_type}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")