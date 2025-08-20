from fastapi import APIRouter, Depends, status, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import LeaveType
from app.core.exceptions import ValidationError
from app.core.utils import get_request_id
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
    settings: Settings = Depends(get_settings)
) -> LeaveApprovalWorkflowOut:
    """Approve or reject a leave request with workflow validation.

    Args:
        approval: The leave approval data including leave_id, approver_id, status, and comments.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        LeaveApprovalWorkflowOut: The created leave approval workflow entry.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), database errors (500), or unexpected errors (500).
    """
    try:
        if approval.leave_id <= 0 or approval.approver_id <= 0:
            raise ValidationError(detail="Invalid leave_id or approver_id")
        request_id = get_request_id(request)
        return await approve_or_reject_leave(approval, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error approving leave: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error approving leave: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

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
    settings: Settings = Depends(get_settings)
) -> LeaveApprovalWorkflowOut:
    """Retrieve a leave approval by ID.

    Args:
        workflow_id: The ID of the leave approval workflow to retrieve.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        LeaveApprovalWorkflowOut: The retrieved leave approval workflow entry.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), database errors (500), or unexpected errors (500).
    """
    try:
        if workflow_id <= 0:
            raise ValidationError(detail="Invalid workflow_id")
        request_id = get_request_id(request)
        return await get_leave_approval(workflow_id, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error retrieving leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/request/{leave_id}",
    response_model=List[LeaveApprovalWorkflowOut],
    summary="List leave approvals by request",
    description="Retrieve a list of approvals for a specific leave request with pagination."
)
async def get_leave_approvals_by_request_endpoint(
    leave_id: int,
    skip: int = 0,
    limit: Optional[int] = None,
    request: Request = Depends(),
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[LeaveApprovalWorkflowOut]:
    """List leave approvals for a leave request with pagination.

    Args:
        leave_id: The ID of the leave request to retrieve approvals for.
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: DEFAULT_PAGE_SIZE).
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[LeaveApprovalWorkflowOut]: List of leave approval workflow entries.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), database errors (500), or unexpected errors (500).
    """
    try:
        if leave_id <= 0:
            raise ValidationError(detail="Invalid leave_id")
        request_id = get_request_id(request)
        return await get_leave_approvals_by_request(leave_id, skip, limit, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error retrieving leave approvals for leave_id {leave_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave approvals for leave_id {leave_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

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
    settings: Settings = Depends(get_settings)
) -> LeaveApprovalWorkflowOut:
    """Update a leave approval workflow entry.

    Args:
        workflow_id: The ID of the leave approval workflow to update.
        update_data: The updated leave approval data.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        LeaveApprovalWorkflowOut: The updated leave approval workflow entry.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), database errors (500), or unexpected errors (500).
    """
    try:
        if workflow_id <= 0:
            raise ValidationError(detail="Invalid workflow_id")
        request_id = get_request_id(request)
        return await update_leave_approval(workflow_id, update_data, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error updating leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

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
    settings: Settings = Depends(get_settings)
) -> None:
    """Soft delete a leave approval workflow entry.

    Args:
        workflow_id: The ID of the leave approval workflow to delete.
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
        if workflow_id <= 0:
            raise ValidationError(detail="Invalid workflow_id")
        request_id = get_request_id(request)
        await delete_leave_approval(workflow_id, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error deleting leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

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
    settings: Settings = Depends(get_settings)
) -> List[WorkflowStepOut]:
    """Define leave approval workflow steps.

    Args:
        workflow_steps: List of workflow steps to create.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[WorkflowStepOut]: List of created workflow steps.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), database errors (500), or unexpected errors (500).
    """
    try:
        for step in workflow_steps:
            if step.leave_id <= 0 or step.approver_id <= 0:
                raise ValidationError(detail="Invalid leave_id or approver_id")
        request_id = get_request_id(request)
        return await define_workflow_steps(workflow_steps, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error defining workflow steps: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error defining workflow steps: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

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
    settings: Settings = Depends(get_settings)
) -> List[WorkflowStepOut]:
    """Retrieve workflow steps by leave type.

    Args:
        leave_type: The leave type to filter workflows (e.g., ANNUAL, SICK).
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[WorkflowStepOut]: List of workflow steps for the specified leave type.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), database errors (500), or unexpected errors (500).
    """
    try:
        if leave_type not in LeaveType:
            raise ValidationError(detail=f"Invalid leave type: {leave_type}")
        request_id = get_request_id(request)
        return await get_workflow_by_type(leave_type, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error retrieving workflow steps for leave_type {leave_type}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving workflow steps for leave_type {leave_type}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")