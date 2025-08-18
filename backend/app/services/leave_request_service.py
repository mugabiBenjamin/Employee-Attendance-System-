from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.leave_requests import LeaveRequests
from app.models.users import Users
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.system_logs import SystemLogs
from app.models.leave_balances import LeaveBalances
from app.schemas.leave_request import LeaveRequestCreate, LeaveRequestUpdate, LeaveRequestOut, LeaveApprovalUpdate
from app.core.config import Settings, get_settings
from app.core.enums import LeaveRequestStatus, SystemAction, Permission
from app.core.mail import send_email
from app.core.exceptions import LeaveRequestNotFoundError, LeaveBalanceNotFoundError, ValidationError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

async def create_leave_request(
    leave_request: LeaveRequestCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.CREATE_LEAVE_REQUEST]))
) -> LeaveRequestOut:
    """Create a new leave request with validation, logging, and email notification."""
    try:
        if leave_request.start_date >= leave_request.end_date:
            raise ValidationError(detail="Start date must be before end date")

        query = select(LeaveRequests).where(
            LeaveRequests.user_id == current_user.user_id,
            LeaveRequests.status != LeaveRequestStatus.REJECTED,
            LeaveRequests.start_date <= leave_request.end_date,
            LeaveRequests.end_date >= leave_request.start_date,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ValidationError(detail="Overlapping leave request exists")

        query = select(LeaveBalances).where(
            LeaveBalances.user_id == current_user.user_id,
            LeaveBalances.leave_type == leave_request.leave_type,
            LeaveBalances.is_active.is_(True),
            LeaveBalances.deleted_at.is_(None)
        )
        result = await db.execute(query)
        leave_balance = result.scalar_one_or_none()
        if not leave_balance:
            raise LeaveBalanceNotFoundError(user_id=current_user.user_id, leave_type=leave_request.leave_type)

        days_requested = (leave_request.end_date - leave_request.start_date).days + 1
        available_days = leave_balance.allocated_days - leave_balance.used_days + leave_balance.carried_forward
        if days_requested > available_days:
            raise ValidationError(detail="Insufficient leave balance")

        db_leave_request = LeaveRequests(
            user_id=current_user.user_id,
            leave_type=leave_request.leave_type,
            start_date=leave_request.start_date,
            end_date=leave_request.end_date,
            days_requested=days_requested,
            reason=leave_request.reason,
            status=LeaveRequestStatus.UNDER_REVIEW,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_leave_request)
        await db.commit()
        await db.refresh(db_leave_request)

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_LEAVE_REQUEST,
            table_affected="leave_requests",
            record_id=db_leave_request.leave_id,
            old_values=None,
            new_values=db_leave_request.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        query = select(Users).join(
            EmployeeHierarchy,
            EmployeeHierarchy.manager_id == Users.user_id
        ).where(
            EmployeeHierarchy.employee_id == current_user.user_id,
            EmployeeHierarchy.is_active.is_(True),
            EmployeeHierarchy.deleted_at.is_(None)
        )
        result = await db.execute(query)
        manager = result.scalar_one_or_none()
        if manager:
            await send_email(
                to_email=manager.email,
                subject="New Leave Request Submitted",
                body=(
                    f"Employee {current_user.first_name} {current_user.last_name} submitted a leave request.\n"
                    f"Details:\n"
                    f"Leave Type: {leave_request.leave_type.value.capitalize()}\n"
                    f"Start Date: {leave_request.start_date}\n"
                    f"End Date: {leave_request.end_date}\n"
                    f"Reason: {leave_request.reason or 'None'}"
                )
            )

        logger.info(f"Leave request created, leave_id: {db_leave_request.leave_id}, user_id: {current_user.user_id}")
        return LeaveRequestOut.model_validate(db_leave_request)

    except (ValidationError, LeaveBalanceNotFoundError):
        raise
    except Exception as e:
        logger.error(f"Error creating leave request for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating leave request"
        )

async def get_leave_request(
    request_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.VIEW_LEAVE_REQUEST, Permission.VIEW_OWN_LEAVE_REQUEST]))
) -> LeaveRequestOut:
    """Retrieve a leave request by ID for the current user or their subordinates."""
    try:
        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == request_id,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        if not any(p in current_user.permissions for p in [Permission.VIEW_LEAVE_REQUEST, Permission.MANAGE_LEAVE]):
            query = query.join(
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
            raise LeaveRequestNotFoundError(leave_id=request_id)

        logger.info(f"Retrieved leave request, leave_id: {request_id}, user_id: {current_user.user_id}")
        return LeaveRequestOut.model_validate(leave_request)

    except LeaveRequestNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error retrieving leave request {request_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving leave request"
        )

async def get_leave_requests(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_LEAVE_REQUEST, Permission.VIEW_OWN_LEAVE_REQUEST]))
) -> List[LeaveRequestOut]:
    """Retrieve a list of leave requests for the current user or their subordinates with pagination."""
    try:
        query = select(LeaveRequests).where(
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        if user_id:
            query = query.where(LeaveRequests.user_id == user_id)
        if not any(p in current_user.permissions for p in [Permission.VIEW_LEAVE_REQUEST, Permission.MANAGE_LEAVE]):
            query = query.join(
                EmployeeHierarchy,
                EmployeeHierarchy.employee_id == LeaveRequests.user_id,
                isouter=True
            ).where(
                (LeaveRequests.user_id == current_user.user_id) |
                (EmployeeHierarchy.manager_id == current_user.user_id)
            )
        query = query.offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
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

async def approve_reject_leave_request(
    leave_id: int,
    approval: LeaveApprovalUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.APPROVE_LEAVE]))
) -> LeaveRequestOut:
    """Approve or reject a leave request, update balance, and notify user."""
    try:
        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == leave_id,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result = await db.execute(query)
        leave_request = result.scalar_one_or_none()
        if not leave_request:
            raise LeaveRequestNotFoundError(leave_id=leave_id)

        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.employee_id == leave_request.user_id,
            EmployeeHierarchy.manager_id == current_user.user_id,
            EmployeeHierarchy.is_active.is_(True),
            EmployeeHierarchy.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise ValidationError(detail="Not authorized to approve this leave request")

        old_values = leave_request.__dict__.copy()
        leave_request.status = approval.status
        leave_request.approved_by = current_user.user_id
        leave_request.approved_at = datetime.now(timezone.utc)
        leave_request.comments = approval.comments
        leave_request.updated_at = datetime.now(timezone.utc)

        if approval.status == LeaveRequestStatus.APPROVED:
            query = select(LeaveBalances).where(
                LeaveBalances.user_id == leave_request.user_id,
                LeaveBalances.leave_type == leave_request.leave_type,
                LeaveBalances.is_active.is_(True),
                LeaveBalances.deleted_at.is_(None)
            )
            result = await db.execute(query)
            leave_balance = result.scalar_one_or_none()
            if not leave_balance:
                raise LeaveBalanceNotFoundError(user_id=leave_request.user_id, leave_type=leave_request.leave_type)
            leave_balance.used_days += leave_request.days_requested
            leave_balance.updated_at = datetime.now(timezone.utc)
            db.add(leave_balance)

        db.add(leave_request)
        await db.commit()
        await db.refresh(leave_request)

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.APPROVE_LEAVE_REQUEST,
            table_affected="leave_requests",
            record_id=leave_request.leave_id,
            old_values=old_values,
            new_values=leave_request.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        query = select(Users).where(Users.user_id == leave_request.user_id)
        result = await db.execute(query)
        employee = result.scalar_one_or_none()
        if employee:
            await send_email(
                to_email=employee.email,
                subject=f"Leave Request {approval.status.value.capitalize()} (ID: {leave_request.leave_id})",
                body=(
                    f"Dear {employee.first_name},\n\n"
                    f"Your leave request (ID: {leave_request.leave_id}) has been {approval.status.value.lower()}.\n"
                    f"Details:\n"
                    f"Leave Type: {leave_request.leave_type.value.capitalize()}\n"
                    f"Start Date: {leave_request.start_date}\n"
                    f"End Date: {leave_request.end_date}\n"
                    f"Comments: {approval.comments or 'None'}\n\n"
                    f"Please contact HR for any questions.\n\n"
                    f"Best regards,\nEmployee Management System"
                )
            )

        logger.info(f"Leave request {leave_id} {approval.status.value} by user_id: {current_user.user_id}")
        return LeaveRequestOut.model_validate(leave_request)

    except (LeaveRequestNotFoundError, LeaveBalanceNotFoundError, ValidationError):
        raise
    except Exception as e:
        logger.error(f"Error approving leave request {leave_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing leave request"
        )