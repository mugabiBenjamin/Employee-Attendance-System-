from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.leave_approval_workflow import LeaveApprovalWorkflow
from app.models.leave_requests import LeaveRequests
from app.models.users import Users
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.system_logs import SystemLogs
from app.schemas.leave_approval_workflow import LeaveApprovalWorkflowCreate, LeaveApprovalWorkflowOut
from app.core.config import settings
from app.core.enums import SystemAction, CorrectionStatus, Permission
from app.core.mail import send_email
from app.core.exceptions import UserNotFoundError, ValidationError
from app.core.security import get_current_user
from app.core.permissions import check_permission, require_permissions
import logging

logger = logging.getLogger(__name__)

async def approve_or_reject_leave(
    db: AsyncSession,
    approval: LeaveApprovalWorkflowCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    _: str = Depends(require_permissions([Permission.APPROVE_LEAVE]))
) -> LeaveApprovalWorkflowOut:
    """
    Approve or reject a leave request with validation, logging, and email notification.
    """
    try:
        # Validate leave request
        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == approval.request_id,
            LeaveRequests.is_active == True,
            LeaveRequests.deleted_at == None
        )
        result = await db.execute(query)
        leave_request = result.scalar_one_or_none()
        if not leave_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Leave request not found"
            )

        # Validate approver
        query = select(Users).where(
            Users.user_id == approval.approver_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        approver = result.scalar_one_or_none()
        if not approver:
            raise UserNotFoundError(detail="Approver not found")

        # Check if approver is in the employee's hierarchy
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.employee_id == leave_request.user_id,
            EmployeeHierarchy.manager_id == approval.approver_id,
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise ValidationError(detail="Approver is not in the employee's hierarchy")

        # Validate approver has APPROVE_LEAVE permission
        from app.services.user_role_service import UserRoleService, get_user_role_service
        user_role_service = get_user_role_service(db)
        user_permissions = await user_role_service.get_user_permissions(approval.approver_id)
        if Permission.APPROVE_LEAVE not in user_permissions:
            raise ValidationError(detail="Approver lacks APPROVE_LEAVE permission")

        # Validate status
        if approval.status not in [CorrectionStatus.APPROVED, CorrectionStatus.REJECTED]:
            raise ValidationError(detail="Invalid status for leave approval")

        # Create approval workflow entry
        db_approval = LeaveApprovalWorkflow(
            leave_id=approval.request_id,
            **LeaveApprovalWorkflowCreate(**approval.model_dump(exclude={'request_id'})).model_dump(),
            action_taken_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_approval)

        # Update leave request status
        leave_request.status = approval.status
        leave_request.updated_at = datetime.now(timezone.utc)
        db.add(leave_request)
        await db.commit()
        await db.refresh(db_approval)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="leave_approval_workflow",
            record_id=db_approval.workflow_id,
            old_values=None,
            new_values=db_approval.__dict__,
            ip_address=request.client.host,  # Updated to use request
            user_agent=request.headers.get("user-agent"),  # Added user_agent
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        # Send email notification to employee
        query = select(Users).where(Users.user_id == leave_request.user_id)
        result = await db.execute(query)
        employee = result.scalar_one_or_none()
        if employee:
            await send_email(
                to_email=employee.email,
                subject=f"Leave Request {approval.status.value}",
                body=f"Your leave request from {leave_request.start_date.date()} to {leave_request.end_date.date()} has been {approval.status.value.lower()}. Comments: {approval.comments or 'None'}"
            )

        logger.info(f"Leave approval processed, workflow_id: {db_approval.workflow_id}, leave_id: {approval.request_id}, status: {approval.status}")
        return LeaveApprovalWorkflowOut.model_validate(db_approval)

    except HTTPException:
        raise
    except ValidationError as e:
        logger.error(f"Validation error processing leave approval for leave_id {approval.request_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error processing leave approval for leave_id {approval.request_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing leave approval"
        )

async def get_leave_approval_by_id(
    db: AsyncSession,
    approval_id: int,
    _: str = Depends(check_permission("view_leave_approval"))
) -> Optional[LeaveApprovalWorkflowOut]:
    """
    Retrieve a leave approval by ID.
    """
    try:
        query = select(LeaveApprovalWorkflow).where(
            LeaveApprovalWorkflow.workflow_id == approval_id,
            LeaveApprovalWorkflow.is_active == True,
            LeaveApprovalWorkflow.deleted_at == None
        )
        result = await db.execute(query)
        approval = result.scalar_one_or_none()

        if not approval:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Leave approval not found"
            )

        return LeaveApprovalWorkflowOut.model_validate(approval)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving leave approval {approval_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving leave approval"
        )

async def get_leave_approvals_by_request(
    db: AsyncSession,
    request_id: int,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    _: str = Depends(check_permission("view_leave_approval"))
) -> List[LeaveApprovalWorkflowOut]:
    """
    Retrieve a list of approvals for a leave request with pagination.
    """
    try:
        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == request_id,
            LeaveRequests.is_active == True,
            LeaveRequests.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Leave request not found"
            )

        query = select(LeaveApprovalWorkflow).where(
            LeaveApprovalWorkflow.leave_id == request_id,
            LeaveApprovalWorkflow.is_active == True,
            LeaveApprovalWorkflow.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        approvals = result.scalars().all()

        logger.info(f"Retrieved {len(approvals)} leave approvals for leave_id: {request_id}")
        return [LeaveApprovalWorkflowOut.model_validate(approval) for approval in approvals]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving leave approvals for leave_id {request_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving leave approvals"
        )