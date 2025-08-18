from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.leave_approval_workflow import LeaveApprovalWorkflow
from app.models.leave_requests import LeaveRequests
from app.models.users import Users
from app.models.employee_hierarchy import EmployeeHierarchy
from app.schemas.leave_approval_workflow import LeaveApprovalWorkflowCreate, LeaveApprovalWorkflowUpdate, LeaveApprovalWorkflowOut, WorkflowStepCreate, WorkflowStepOut
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, LeaveRequestStatus, Permission
from app.core.mail import send_email
from app.core.exceptions import DatabaseError, LeaveApprovalWorkflowError, UserNotFoundError, ValidationError, LeaveRequestNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db
from app.services.user_role_service import get_user_permissions
from app.services.system_log_service import create_system_log
from app.schemas.system_log import SystemLogCreate
import logging

logger = logging.getLogger(__name__)

def get_request_id(request: Request) -> Optional[str]:
    """Extract request_id from the request state."""
    return request.state.request_id if hasattr(request.state, "request_id") else None

async def approve_or_reject_leave(
    approval: LeaveApprovalWorkflowCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.APPROVE_LEAVE]))
) -> LeaveApprovalWorkflowOut:
    """
    Approve or reject a leave request with validation, logging, and email notification."""
    try:
        # Validate leave request
        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == approval.request_id,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result = await db.execute(query)
        leave_request = result.scalar_one_or_none()
        if not leave_request:
            raise LeaveRequestNotFoundError(leave_id=approval.request_id)

        # Validate approver
        query = select(Users).where(
            Users.user_id == approval.approver_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        approver = result.scalar_one_or_none()
        if not approver:
            raise UserNotFoundError(user_id=approval.approver_id)

        # Validate hierarchy
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.employee_id == leave_request.user_id,
            EmployeeHierarchy.manager_id == approval.approver_id,
            EmployeeHierarchy.is_active.is_(True),
            EmployeeHierarchy.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise ValidationError(detail="Approver is not in the employee's hierarchy")

        # Validate permissions
        user_permissions = await get_user_permissions(approval.approver_id, db, request_id)
        if Permission.APPROVE_LEAVE not in user_permissions and approval.approver_id != current_user.user_id:
            raise ValidationError(detail="Approver lacks APPROVE_LEAVE permission")

        # Validate status
        if approval.status not in [LeaveRequestStatus.APPROVED, LeaveRequestStatus.REJECTED]:
            raise ValidationError(detail="Invalid status for leave approval")

        # Create approval entry
        db_approval = LeaveApprovalWorkflow(
            leave_id=approval.request_id,
            approver_id=approval.approver_id,
            status=approval.status,
            comments=approval.comments,
            level=approval.level,
            action_taken_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_approval)

        # Update leave request
        leave_request.status = approval.status
        leave_request.updated_at = datetime.now(timezone.utc)
        db.add(leave_request)
        await db.commit()
        await db.refresh(db_approval)

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.APPROVE_LEAVE,
            table_affected="leave_approval_workflow",
            record_id=db_approval.workflow_id,
            old_values=None,
            new_values=db_approval.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        # Send email notification
        query = select(Users).where(Users.user_id == leave_request.user_id)
        result = await db.execute(query)
        employee = result.scalar_one_or_none()
        if employee:
            await send_email(
                to_email=employee.email,
                subject=f"Leave Request {approval.status.value}",
                body=f"Your leave request from {leave_request.start_date.date()} to {leave_request.end_date.date()} has been {approval.status.value.lower()}. Comments: {approval.comments or 'None'}"
            )

        logger.info(
            f"Leave approval processed, workflow_id: {db_approval.workflow_id}, leave_id: {approval.request_id}, status: {approval.status}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return LeaveApprovalWorkflowOut.model_validate(db_approval)

    except LeaveRequestNotFoundError as e:
        logger.error(f"Leave request not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error processing leave approval: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error processing leave approval: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_leave_approval(
    approval_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_LEAVE_APPROVAL]))
) -> LeaveApprovalWorkflowOut:
    """
    Retrieve a leave approval by ID with authorization checks."""
    try:
        query = select(LeaveApprovalWorkflow).where(
            LeaveApprovalWorkflow.workflow_id == approval_id,
            LeaveApprovalWorkflow.is_active.is_(True),
            LeaveApprovalWorkflow.deleted_at.is_(None)
        )
        result = await db.execute(query)
        approval = result.scalar_one_or_none()

        if not approval:
            raise LeaveApprovalWorkflowError(workflow_id=approval_id)

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db, request_id)
        if not any(p in user_permissions for p in [Permission.VIEW_LEAVE_APPROVAL, Permission.MANAGE_LEAVE]) and approval.approver_id != current_user.user_id:
            query = select(LeaveRequests).where(
                LeaveRequests.leave_id == approval.leave_id,
                LeaveRequests.user_id == current_user.user_id
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view this leave approval"
                )

        logger.info(
            f"Retrieved leave approval, workflow_id: {approval_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return LeaveApprovalWorkflowOut.model_validate(approval)

    except LeaveApprovalWorkflowError as e:
        logger.error(f"Leave approval not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Forbidden access to leave approval {approval_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except DatabaseError as e:
        logger.error(f"Database error retrieving leave approval {approval_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave approval {approval_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_leave_approvals_by_request(
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_LEAVE_APPROVAL]))
) -> List[LeaveApprovalWorkflowOut]:
    """
    Retrieve a list of approvals for a leave request with pagination."""
    try:
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")

        # Validate leave request
        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == request_id,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result = await db.execute(query)
        leave_request = result.scalar_one_or_none()
        if not leave_request:
            raise LeaveRequestNotFoundError(leave_id=request_id)

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db, request_id)
        if not any(p in user_permissions for p in [Permission.VIEW_LEAVE_APPROVAL, Permission.MANAGE_LEAVE]) and leave_request.user_id != current_user.user_id:
            query = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == leave_request.user_id,
                EmployeeHierarchy.manager_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view approvals for this leave request"
                )

        # Retrieve approvals
        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = select(LeaveApprovalWorkflow).where(
            LeaveApprovalWorkflow.leave_id == request_id,
            LeaveApprovalWorkflow.is_active.is_(True),
            LeaveApprovalWorkflow.deleted_at.is_(None)
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        approvals = result.scalars().all()

        logger.info(
            f"Retrieved {len(approvals)} leave approvals for leave_id: {request_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [LeaveApprovalWorkflowOut.model_validate(approval) for approval in approvals]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except LeaveRequestNotFoundError as e:
        logger.error(f"Leave request not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Forbidden access to leave approvals for leave_id {request_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except DatabaseError as e:
        logger.error(f"Database error retrieving leave approvals for leave_id {request_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave approvals for leave_id {request_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def define_workflow_steps(
    request: Request,
    workflow_steps: List[WorkflowStepCreate],
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.MANAGE_LEAVE]))
) -> List[WorkflowStepOut]:
    """
    Define leave approval workflow steps with validation and logging."""
    try:
        if not workflow_steps:
            raise ValidationError(detail="At least one workflow step is required")

        # Validate leave request
        leave_id = workflow_steps[0].request_id
        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == leave_id,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise LeaveRequestNotFoundError(leave_id=leave_id)

        # Validate approvers
        user_ids = {step.approver_id for step in workflow_steps}
        query = select(Users).where(
            Users.user_id.in_(user_ids),
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        users = {user.user_id: user for user in result.scalars().all()}
        if len(users) != len(user_ids):
            raise UserNotFoundError(detail="One or more approvers not found")

        # Validate levels and permissions
        created_steps = []
        for step in workflow_steps:
            if step.level < 1 or step.level > 5:
                raise ValidationError(detail=f"Invalid level {step.level} for workflow step")
            if step.request_id != leave_id:
                raise ValidationError(detail="All steps must belong to the same leave request")
            if step.approver_id not in users:
                raise UserNotFoundError(user_id=step.approver_id)
            user_permissions = await get_user_permissions(step.approver_id, db, request_id)
            if Permission.APPROVE_LEAVE not in user_permissions:
                raise ValidationError(detail=f"Approver {step.approver_id} lacks APPROVE_LEAVE permission")

            db_step = LeaveApprovalWorkflow(
                leave_id=step.request_id,
                approver_id=step.approver_id,
                level=step.level,
                status=LeaveRequestStatus.UNDER_REVIEW,
                comments=None,
                action_taken_at=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db.add(db_step)
            created_steps.append(db_step)

        await db.commit()
        for step in created_steps:
            await db.refresh(step)

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DEFINE_WORKFLOW,
            table_affected="leave_approval_workflow",
            record_id=None,
            old_values=None,
            new_values={step.workflow_id: step.__dict__ for step in created_steps},
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Defined {len(created_steps)} workflow steps for leave_id: {leave_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [WorkflowStepOut.model_validate(step) for step in created_steps]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except LeaveRequestNotFoundError as e:
        logger.error(f"Leave request not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error defining workflow steps: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error defining workflow steps: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_workflow_by_type(
    leave_type: str,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_WORKFLOWS]))
) -> List[WorkflowStepOut]:
    """
    Retrieve workflow steps for a specific leave type with authorization checks."""
    try:
        # Retrieve leave requests by type
        query = select(LeaveRequests).where(
            LeaveRequests.leave_type == leave_type,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result = await db.execute(query)
        leave_requests = result.scalars().all()
        if not leave_requests:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No leave requests found for leave type {leave_type}"
            )

        # Retrieve workflow steps
        leave_ids = [lr.leave_id for lr in leave_requests]
        query = select(LeaveApprovalWorkflow).where(
            LeaveApprovalWorkflow.leave_id.in_(leave_ids),
            LeaveApprovalWorkflow.is_active.is_(True),
            LeaveApprovalWorkflow.deleted_at.is_(None)
        )
        result = await db.execute(query)
        steps = result.scalars().all()

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db, request_id)
        if not any(p in user_permissions for p in [Permission.VIEW_WORKFLOWS, Permission.MANAGE_LEAVE]):
            allowed_leave_ids = []
            for lr in leave_requests:
                if lr.user_id == current_user.user_id:
                    allowed_leave_ids.append(lr.leave_id)
                else:
                    query = select(EmployeeHierarchy).where(
                        EmployeeHierarchy.employee_id == lr.user_id,
                        EmployeeHierarchy.manager_id == current_user.user_id,
                        EmployeeHierarchy.is_active.is_(True),
                        EmployeeHierarchy.deleted_at.is_(None)
                    )
                    result = await db.execute(query)
                    if result.scalar_one_or_none():
                        allowed_leave_ids.append(lr.leave_id)
            steps = [step for step in steps if step.leave_id in allowed_leave_ids]

        logger.info(
            f"Retrieved {len(steps)} workflow steps for leave_type: {leave_type}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [WorkflowStepOut.model_validate(step) for step in steps]

    except HTTPException as e:
        logger.error(f"Error retrieving workflow steps for leave_type {leave_type}: {str(e)}", extra={"request_id": request_id})
        raise
    except DatabaseError as e:
        logger.error(f"Database error retrieving workflow steps for leave_type {leave_type}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving workflow steps for leave_type {leave_type}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")