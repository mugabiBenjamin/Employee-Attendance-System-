from typing import List, Optional
from fastapi import HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.leave_requests import LeaveRequests
from app.models.users import Users
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.system_logs import SystemLogs
from app.models.leave_balances import LeaveBalances
from app.schemas.leave_request import LeaveRequestCreate, LeaveRequestOut
from app.core.config import settings
from app.core.enums import LeaveRequestStatus, SystemAction
from app.core.mail import send_email
from app.core.security import get_current_user
from app.core.permissions import check_permission
import logging

logger = logging.getLogger(__name__)

async def create_leave_request(
    db: AsyncSession,
    leave_request: LeaveRequestCreate,
    current_user: Users = Depends(get_current_user),
    _: str = Depends(check_permission("create_leave_request"))
) -> LeaveRequestOut:
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
            LeaveRequests.status != LeaveRequestStatus.REJECTED,
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

        # Validate leave balance
        query = select(LeaveBalances).where(
            LeaveBalances.user_id == current_user.user_id,
            LeaveBalances.leave_type == leave_request.leave_type,
            LeaveBalances.is_active == True,
            LeaveBalances.deleted_at == None
        )
        result = await db.execute(query)
        leave_balance = result.scalar_one_or_none()
        if not leave_balance:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No leave balance available for this leave type"
            )

        days_requested = (leave_request.end_date.date() - leave_request.start_date.date()).days + 1
        available_days = leave_balance.allocated_days - leave_balance.used_days + leave_balance.carried_forward
        if days_requested > available_days:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient leave balance"
            )

        # Create leave request
        db_leave_request = LeaveRequests(
            user_id=current_user.user_id,
            leave_type=leave_request.leave_type,
            start_date=leave_request.start_date,
            end_date=leave_request.end_date,
            days_requested=days_requested,
            reason=leave_request.reason,
            status=leave_request.status,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_leave_request)
        await db.commit()
        await db.refresh(db_leave_request)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="leave_requests",
            record_id=db_leave_request.leave_id,
            old_values=None,
            new_values=db_leave_request.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        # Send email notification to manager
        query = select(Users).join(
            EmployeeHierarchy,
            EmployeeHierarchy.manager_id == Users.user_id
        ).where(
            EmployeeHierarchy.employee_id == current_user.user_id,
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
        result = await db.execute(query)
        manager = result.scalar_one_or_none()
        if manager:
            await send_email(
                to_email=manager.email,
                subject="New Leave Request Submitted",
                body=f"Employee {current_user.first_name} {current_user.last_name} submitted a leave request from {leave_request.start_date.date()} to {leave_request.end_date.date()}."
            )

        logger.info(f"Leave request created, leave_id: {db_leave_request.leave_id}, user_id: {current_user.user_id}")
        return LeaveRequestOut.model_validate(db_leave_request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating leave request for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating leave request"
        )

async def get_leave_request_by_id(
    db: AsyncSession,
    request_id: int,
    current_user: Users = Depends(get_current_user),
    _: str = Depends(check_permission("view_leave_request"))
) -> Optional[LeaveRequestOut]:
    """
    Retrieve a leave request by ID for the current user or their subordinates.
    """
    try:
        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == request_id,
            LeaveRequests.is_active == True,
            LeaveRequests.deleted_at == None
        ).join(
            EmployeeHierarchy,
            EmployeeHierarchy.employee_id == LeaveRequests.user_id,
            isouter=True
        ).where(
            (LeaveRequests.user_id == current_user.user_id) |
            (EmployeeHierarchy.manager_id == current_user.user_id)
        )
        result = await db.execute(query)
        leave_request = result.scalar_one_or_none()

        if not leave_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Leave request not found or not authorized"
            )

        logger.info(f"Retrieved leave request, leave_id: {request_id}, user_id: {current_user.user_id}")
        return LeaveRequestOut.model_validate(leave_request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving leave request {request_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving leave request"
        )

async def get_user_leave_requests(
    db: AsyncSession,
    current_user: Users = Depends(get_current_user),
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    _: str = Depends(check_permission("view_leave_request"))
) -> List[LeaveRequestOut]:
    """
    Retrieve a list of leave requests for the current user or their subordinates with pagination.
    """
    try:
        query = select(LeaveRequests).where(
            LeaveRequests.is_active == True,
            LeaveRequests.deleted_at == None
        ).join(
            EmployeeHierarchy,
            EmployeeHierarchy.employee_id == LeaveRequests.user_id,
            isouter=True
        ).where(
            (LeaveRequests.user_id == current_user.user_id) |
            (EmployeeHierarchy.manager_id == current_user.user_id)
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