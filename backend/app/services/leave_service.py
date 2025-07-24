from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict
from app.models.leave_requests import LeaveRequests
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.schemas.leave_request import LeaveRequestCreate, LeaveRequestOut
from app.core.config import settings
from app.core.enums import SystemAction, LeaveStatus
from app.core.email import send_email_notification
import logging

logger = logging.getLogger(__name__)

class LeaveRequestCreateInternal(BaseModel):
    user_id: int
    leave_type: str
    start_date: datetime
    end_date: datetime
    reason: Optional[str] = None
    status: LeaveStatus = LeaveStatus.PENDING

    model_config = ConfigDict(from_attributes=True)

async def create_leave_request(db: AsyncSession, leave_request: LeaveRequestCreate, current_user: Users) -> LeaveRequestOut:
    """
    Create a new leave request with validation, logging, and email notification.
    """
    try:
        # Validate dates
        if leave_request.start_date >= leave_request.end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Start date must be before end date"
            )

        # Check for overlapping leave requests
        query = select(LeaveRequests).where(
            LeaveRequests.user_id == current_user.user_id,
            LeaveRequests.status != LeaveStatus.REJECTED,
            LeaveRequests.start_date <= leave_request.end_date,
            LeaveRequests.end_date >= leave_request.start_date,
            LeaveRequests.is_active == True,
            LeaveRequests.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Overlapping leave request exists"
            )

        # Create leave request
        db_leave_request = LeaveRequests(
            **LeaveRequestCreateInternal(
                user_id=current_user.user_id,
                leave_type=leave_request.leave_type,
                start_date=leave_request.start_date,
                end_date=leave_request.end_date,
                reason=leave_request.reason
            ).model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_leave_request)
        await db.commit()
        await db.refresh(db_leave_request)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.LEAVE_REQUEST_SUBMITTED,
            table_affected="leave_requests",
            record_id=db_leave_request.request_id,
            old_values=None,
            new_values=db_leave_request.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        # Send email notification to manager (assuming manager_id is in employee_hierarchy)
        query = select(Users).join(
            app.models.employee_hierarchy.EmployeeHierarchy,
            app.models.employee_hierarchy.EmployeeHierarchy.manager_id == Users.user_id
        ).where(
            app.models.employee_hierarchy.EmployeeHierarchy.employee_id == current_user.user_id
        )
        result = await db.execute(query)
        manager = result.scalar_one_or_none()
        if manager:
            await send_email_notification(
                to_email=manager.email,
                subject="New Leave Request Submitted",
                body=f"Employee {current_user.first_name} {current_user.last_name} submitted a leave request from {leave_request.start_date.date()} to {leave_request.end_date.date()}."
            )

        logger.info(f"Leave request created, request_id: {db_leave_request.request_id}, user_id: {current_user.user_id}")
        return LeaveRequestOut.model_validate(db_leave_request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating leave request for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating leave request"
        )

async def get_leave_request_by_id(db: AsyncSession, request_id: int, current_user: Users) -> Optional[LeaveRequestOut]:
    """
    Retrieve a leave request by ID for the current user.
    """
    try:
        query = select(LeaveRequests).where(
            LeaveRequests.request_id == request_id,
            LeaveRequests.user_id == current_user.user_id,
            LeaveRequests.is_active == True,
            LeaveRequests.deleted_at == None
        )
        result = await db.execute(query)
        leave_request = result.scalar_one_or_none()

        if not leave_request:
            return None

        logger.info(f"Retrieved leave request, request_id: {request_id}, user_id: {current_user.user_id}")
        return LeaveRequestOut.model_validate(leave_request)

    except Exception as e:
        logger.error(f"Error retrieving leave request {request_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving leave request"
        )

async def get_user_leave_requests(db: AsyncSession, current_user: Users, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[LeaveRequestOut]:
    """
    Retrieve a list of leave requests for the current user with pagination.
    """
    try:
        query = select(LeaveRequests).where(
            LeaveRequests.user_id == current_user.user_id,
            LeaveRequests.is_active == True,
            LeaveRequests.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        leave_requests = result.scalars().all()

        logger.info(f"Retrieved {len(leave_requests)} leave requests for user_id: {current_user.user_id}")
        return [LeaveRequestOut.model_validate(req) for req in leave_requests]

    except Exception as e:
        logger.error(f"Error retrieving leave requests for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving leave requests"
        )