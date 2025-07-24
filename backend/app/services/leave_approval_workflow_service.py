from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict
from app.models.leave_approval_workflow import LeaveApprovalWorkflow
from app.models.leave_requests import LeaveRequests
from app.models.users import Users
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.system_logs import SystemLogs
from app.schemas.leave_approval_workflow import LeaveApprovalCreate, LeaveApprovalOut
from app.core.config import settings
from app.core.enums import SystemAction, LeaveStatus
from app.core.mail import send_email_notification
import logging

logger = logging.getLogger(__name__)

class LeaveApprovalCreateInternal(BaseModel):
    request_id: int
    approver_id: int
    status: LeaveStatus
    comments: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

async def approve_or_reject_leave(db: AsyncSession, approval: LeaveApprovalCreate, current_user: Users) -> LeaveApprovalOut:
    """
    Approve or reject a leave request with validation, logging, and email notification.
    """
    try:
        # Validate leave request
        query = select(LeaveRequests).where(
            LeaveRequests.request_id == approval.request_id,
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Approver not found"
            )

        # Check if approver is authorized (e.g., manager of the employee)
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.employee_id == leave_request.user_id,
            EmployeeHierarchy.manager_id == approval.approver_id,
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to approve this leave request"
            )

        # Create approval workflow entry
        db_approval = LeaveApprovalWorkflow(
            **LeaveApprovalCreateInternal(**approval.model_dump()).model_dump(),
            approval_date=datetime.now(timezone.utc),
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
            action=SystemAction.LEAVE_APPROVAL_PROCESSED,
            table_affected="leave_approval_workflow",
            record_id=db_approval.approval_id,
            old_values=None,
            new_values=db_approval.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        # Send email notification to employee
        query = select(Users).where(Users.user_id == leave_request.user_id)
        result = await db.execute(query)
        employee = result.scalar_one_or_none()
        if employee:
            await send_email_notification(
                to_email=employee.email,
                subject=f"Leave Request {approval.status.value}",
                body=f"Your leave request from {leave_request.start_date.date()} to {leave_request.end_date.date()} has been {approval.status.value.lower()}. Comments: {approval.comments or 'None'}"
            )

        logger.info(f"Leave approval processed, approval_id: {db_approval.approval_id}, request_id: {approval.request_id}, status: {approval.status}")
        return LeaveApprovalOut.model_validate(db_approval)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing leave approval for request_id {approval.request_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing leave approval"
        )

async def get_leave_approval_by_id(db: AsyncSession, approval_id: int) -> Optional[LeaveApprovalOut]:
    """
    Retrieve a leave approval by ID.
    """
    try:
        query = select(LeaveApprovalWorkflow).where(
            LeaveApprovalWorkflow.approval_id == approval_id,
            LeaveApprovalWorkflow.is_active == True,
            LeaveApprovalWorkflow.deleted_at == None
        )
        result = await db.execute(query)
        approval = result.scalar_one_or_none()

        if not approval:
            return None

        return LeaveApprovalOut.model_validate(approval)

    except Exception as e:
        logger.error(f"Error retrieving leave approval {approval_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving leave approval"
        )

async def get_leave_approvals_by_request(db: AsyncSession, request_id: int, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[LeaveApprovalOut]:
    """
    Retrieve a list of approvals for a leave request with pagination.
    """
    try:
        query = select(LeaveRequests).where(
            LeaveRequests.request_id == request_id,
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
            LeaveApprovalWorkflow.request_id == request_id,
            LeaveApprovalWorkflow.is_active == True,
            LeaveApprovalWorkflow.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        approvals = result.scalars().all()

        logger.info(f"Retrieved {len(approvals)} leave approvals for request_id: {request_id}")
        return [LeaveApprovalOut.model_validate(approval) for approval in approvals]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving leave approvals for request_id {request_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving leave approvals"
        )