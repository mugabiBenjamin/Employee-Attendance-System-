from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.models.leave_approval_workflow import LeaveApprovalWorkflow
from app.models.leave_requests import LeaveRequests
from app.models.users import Users
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.leave_balances import LeaveBalances
from app.models.leave_policies import LeavePolicies
from app.schemas.leave_approval_workflow import (
    LeaveApprovalWorkflowCreate,
    LeaveApprovalWorkflowUpdate,
    LeaveApprovalWorkflowOut,
    WorkflowStepCreate,
    WorkflowStepOut
)
from app.schemas.system_log import SystemLogCreate
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, LeaveRequestStatus, Permission, LeaveType
from app.core.mail import send_email
from app.core.exceptions import DatabaseError, LeaveApprovalWorkflowError, UserNotFoundError, ValidationError, LeaveRequestNotFoundError, LeaveBalanceNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions, invalidate_user_cache, get_user_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_leave_request_exists, validate_user_exists
from app.core.utils import get_request_id
from app.services.system_log_service import create_system_log
from app.services.leave_request_service import validate_no_overlapping_leave_requests
import logging

logger = logging.getLogger(__name__)

async def validate_leave_approval_exists(db: AsyncSession, workflow_id: int, request_id: Optional[str] = None) -> None:
    """Validate that a leave approval workflow exists."""
    query = select(LeaveApprovalWorkflow).where(
        LeaveApprovalWorkflow.workflow_id == workflow_id,
        LeaveApprovalWorkflow.is_active.is_(True),
        LeaveApprovalWorkflow.deleted_at.is_(None)
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise LeaveApprovalWorkflowError(workflow_id=workflow_id)

async def validate_workflow_progression(
    db: AsyncSession,
    leave_id: int,
    level: int,
    request_id: Optional[str] = None
) -> None:
    """Validate that previous workflow levels are approved."""
    query = select(LeaveApprovalWorkflow).where(
        LeaveApprovalWorkflow.leave_id == leave_id,
        LeaveApprovalWorkflow.level < level,
        LeaveApprovalWorkflow.is_active.is_(True),
        LeaveApprovalWorkflow.deleted_at.is_(None),
        LeaveApprovalWorkflow.status != LeaveRequestStatus.APPROVED
    )
    result = await db.execute(query)
    if result.scalars().first():
        raise ValidationError(detail=f"Previous workflow levels must be approved before level {level}")

async def approve_or_reject_leave(
    approval: LeaveApprovalWorkflowCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.APPROVE_LEAVE]))
) -> LeaveApprovalWorkflowOut:
    """Approve or reject a leave request with validation, logging, and notification."""
    try:
        if approval.leave_id <= 0 or approval.approver_id <= 0:
            raise ValidationError(detail="Invalid leave_id or approver_id")
        if approval.level < 1 or approval.level > settings.MAX_WORKFLOW_LEVELS:
            raise ValidationError(detail=f"Invalid workflow level: {approval.level}")
        if approval.status not in [LeaveRequestStatus.APPROVED, LeaveRequestStatus.REJECTED]:
            raise ValidationError(detail="Invalid status for leave approval")

        # Validate leave request
        await validate_leave_request_exists(db, approval.leave_id, request_id)
        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == approval.leave_id,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result = await db.execute(query)
        leave_request = result.scalar_one_or_none()
        if not leave_request:
            raise LeaveRequestNotFoundError(leave_id=approval.leave_id)

        # Prevent re-approval/rejection
        if leave_request.status != LeaveRequestStatus.UNDER_REVIEW:
            raise ValidationError(detail=f"Leave request is already {leave_request.status.value.lower()}")

        # Validate approver
        await validate_user_exists(db, approval.approver_id, request_id)

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db, request_id)
        if not any(p == Permission.MANAGE_LEAVE.value for p in user_permissions) and approval.approver_id != current_user.user_id:
            query_hierarchy = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == leave_request.user_id,
                EmployeeHierarchy.supervisor_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result_hierarchy = await db.execute(query_hierarchy)
            if not result_hierarchy.scalar_one_or_none():
                raise ValidationError(detail="Not authorized to approve this leave request")

        # Validate workflow progression
        await validate_workflow_progression(db, approval.leave_id, approval.level, request_id)

        # Validate no overlapping leave requests or holidays if approved
        if approval.status == LeaveRequestStatus.APPROVED:
            await validate_no_overlapping_leave_requests(
                db, leave_request.user_id, leave_request.start_date, leave_request.end_date, approval.leave_id, request_id, settings
            )
            # Validate leave balance
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
            available_days = leave_balance.allocated_days - leave_balance.used_days + leave_balance.carried_forward
            if leave_request.days_requested > available_days:
                raise ValidationError(detail=f"Insufficient leave balance: {available_days} days available, {leave_request.days_requested} days requested")
            # Validate leave policy
            query_policy = select(LeavePolicies).where(
                LeavePolicies.leave_type == leave_request.leave_type,
                LeavePolicies.is_active.is_(True),
                LeavePolicies.deleted_at.is_(None)
            )
            result_policy = await db.execute(query_policy)
            leave_policy = result_policy.scalar_one_or_none()
            if leave_policy and leave_request.days_requested > leave_policy.max_days:
                raise ValidationError(detail=f"Requested days ({leave_request.days_requested}) exceed policy limit ({leave_policy.max_days}) for {leave_request.leave_type.value}")

        # Create approval entry
        db_approval = LeaveApprovalWorkflow(
            leave_id=approval.leave_id,
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
        leave_request.approved_by = approval.approver_id
        leave_request.approved_at = datetime.now(timezone.utc)
        leave_request.updated_at = datetime.now(timezone.utc)
        if approval.status == LeaveRequestStatus.APPROVED:
            leave_balance.used_days += leave_request.days_requested
            leave_balance.updated_at = datetime.now(timezone.utc)
            db.add(leave_balance)
        db.add(leave_request)
        await db.commit()
        await db.refresh(db_approval)

        # Notify employee, supervisor, and admins
        eat_tz = ZoneInfo("Africa/Nairobi")
        current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
        recipients = []
        query_employee = select(Users).where(
            Users.user_id == leave_request.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_employee = await db.execute(query_employee)
        employee = result_employee.scalar_one_or_none()
        if employee:
            recipients.append((employee.email, employee.first_name))
        query_manager = select(Users).join(
            EmployeeHierarchy,
            and_(
                EmployeeHierarchy.supervisor_id == Users.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
        ).where(
            EmployeeHierarchy.employee_id == leave_request.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_manager = await db.execute(query_manager)
        manager = result_manager.scalar_one_or_none()
        if manager:
            recipients.append((manager.email, manager.first_name))
        admins = await get_user_permissions(Permission.MANAGE_LEAVE, db)
        recipients.extend([(admin.email, admin.first_name) for admin in admins])
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"Leave Request {approval.status.value.capitalize()} (ID: {leave_request.leave_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"The leave request (ID: {leave_request.leave_id}) for user ID {leave_request.user_id} has been {approval.status.value.lower()}.\n"
                    f"Details:\n"
                    f"Leave Type: {leave_request.leave_type.value.capitalize()}\n"
                    f"Start Date: {leave_request.start_date}\n"
                    f"End Date: {leave_request.end_date}\n"
                    f"Days Requested: {leave_request.days_requested}\n"
                    f"Comments: {approval.comments or 'None'}\n"
                    f"Approved At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        # Invalidate cache
        invalidate_user_cache(leave_request.user_id)
        await invalidate_cache_prefix("leave_approval_workflow")
        await invalidate_cache_prefix("leave_requests")
        logger.info(f"Cache invalidated for leave_approval_workflow, leave_requests, and user_id: {leave_request.user_id}", extra={"request_id": request_id})

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.APPROVE_LEAVE_REQUEST,
            table_affected="leave_approval_workflow",
            record_id=db_approval.workflow_id,
            old_values=None,
            new_values=db_approval.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Leave approval processed, workflow_id: {db_approval.workflow_id}, leave_id: {approval.leave_id}, status: {approval.status}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return LeaveApprovalWorkflowOut.model_validate(db_approval)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (LeaveRequestNotFoundError, UserNotFoundError, LeaveBalanceNotFoundError) as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error processing leave approval: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing leave approval")

async def get_leave_approval(
    workflow_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_LEAVE_APPROVAL]))
) -> LeaveApprovalWorkflowOut:
    """Retrieve a leave approval by ID with authorization checks and caching."""
    try:
        if workflow_id <= 0:
            raise ValidationError(detail="Invalid workflow_id")

        cache_key = f"leave_approval_workflow:{workflow_id}"
        cached_approval = await get_cache(cache_key)
        if cached_approval:
            logger.info(f"Cache hit for leave_approval_workflow:{workflow_id}", extra={"request_id": request_id})
            return LeaveApprovalWorkflowOut(**cached_approval)

        await validate_leave_approval_exists(db, workflow_id, request_id)

        query = select(LeaveApprovalWorkflow).where(
            LeaveApprovalWorkflow.workflow_id == workflow_id,
            LeaveApprovalWorkflow.is_active.is_(True),
            LeaveApprovalWorkflow.deleted_at.is_(None)
        )
        result = await db.execute(query)
        approval = result.scalar_one_or_none()
        if not approval:
            raise LeaveApprovalWorkflowError(workflow_id=workflow_id)

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db, request_id)
        if not any(p in [Permission.VIEW_LEAVE_APPROVAL.value, Permission.MANAGE_LEAVE.value] for p in user_permissions):
            query_lr = select(LeaveRequests).where(
                LeaveRequests.leave_id == approval.leave_id,
                LeaveRequests.is_active.is_(True),
                LeaveRequests.deleted_at.is_(None)
            )
            result_lr = await db.execute(query_lr)
            leave_request = result_lr.scalar_one_or_none()
            if leave_request.user_id != current_user.user_id and approval.approver_id != current_user.user_id:
                query_hierarchy = select(EmployeeHierarchy).where(
                    EmployeeHierarchy.employee_id == leave_request.user_id,
                    EmployeeHierarchy.supervisor_id == current_user.user_id,
                    EmployeeHierarchy.is_active.is_(True),
                    EmployeeHierarchy.deleted_at.is_(None)
                )
                result_hierarchy = await db.execute(query_hierarchy)
                if not result_hierarchy.scalar_one_or_none():
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized to view this leave approval"
                    )

        approval_dict = LeaveApprovalWorkflowOut.model_validate(approval).model_dump()
        await set_cache(cache_key, approval_dict, ttl=300)
        logger.info(f"Cache set for leave_approval_workflow:{workflow_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved leave approval, workflow_id: {workflow_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return LeaveApprovalWorkflowOut.model_validate(approval)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except LeaveApprovalWorkflowError as e:
        logger.error(f"Leave approval not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Forbidden access to leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave approval")

async def get_leave_approvals_by_request(
    leave_id: int,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_LEAVE_APPROVAL]))
) -> List[LeaveApprovalWorkflowOut]:
    """Retrieve a list of approvals for a leave request with pagination and caching."""
    try:
        if leave_id <= 0:
            raise ValidationError(detail="Invalid leave_id")
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")

        cache_key = f"leave_approvals_by_request:{leave_id}:{skip}:{limit or settings.DEFAULT_PAGE_SIZE}"
        cached_approvals = await get_cache(cache_key)
        if cached_approvals:
            logger.info(f"Cache hit for leave_approvals_by_request:{leave_id}", extra={"request_id": request_id})
            return [LeaveApprovalWorkflowOut(**approval) for approval in cached_approvals]

        await validate_leave_request_exists(db, leave_id, request_id)

        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == leave_id,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result = await db.execute(query)
        leave_request = result.scalar_one_or_none()
        if not leave_request:
            raise LeaveRequestNotFoundError(leave_id=leave_id)

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db, request_id)
        if not any(p in [Permission.VIEW_LEAVE_APPROVAL.value, Permission.MANAGE_LEAVE.value] for p in user_permissions):
            if leave_request.user_id != current_user.user_id:
                query_hierarchy = select(EmployeeHierarchy).where(
                    EmployeeHierarchy.employee_id == leave_request.user_id,
                    EmployeeHierarchy.supervisor_id == current_user.user_id,
                    EmployeeHierarchy.is_active.is_(True),
                    EmployeeHierarchy.deleted_at.is_(None)
                )
                result_hierarchy = await db.execute(query_hierarchy)
                if not result_hierarchy.scalar_one_or_none():
                    query_approver = select(LeaveApprovalWorkflow).where(
                        LeaveApprovalWorkflow.leave_id == leave_id,
                        LeaveApprovalWorkflow.approver_id == current_user.user_id,
                        LeaveApprovalWorkflow.is_active.is_(True),
                        LeaveApprovalWorkflow.deleted_at.is_(None)
                    )
                    result_approver = await db.execute(query_approver)
                    if not result_approver.scalar_one_or_none():
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Not authorized to view approvals for this leave request"
                        )

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = select(LeaveApprovalWorkflow).where(
            LeaveApprovalWorkflow.leave_id == leave_id,
            LeaveApprovalWorkflow.is_active.is_(True),
            LeaveApprovalWorkflow.deleted_at.is_(None)
        ).order_by(LeaveApprovalWorkflow.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        approvals = result.scalars().all()

        approvals_dict = [LeaveApprovalWorkflowOut.model_validate(approval).model_dump() for approval in approvals]
        await set_cache(cache_key, approvals_dict, ttl=300)
        logger.info(f"Cache set for leave_approvals_by_request:{leave_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(approvals)} leave approvals for leave_id: {leave_id}",
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
        logger.error(f"Forbidden access to leave approvals for leave_id {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave approvals for leave_id {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave approvals")

async def update_leave_approval(
    workflow_id: int,
    update_data: LeaveApprovalWorkflowUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.MANAGE_LEAVE]))
) -> LeaveApprovalWorkflowOut:
    """Update a leave approval workflow entry with validation, logging, and notification."""
    try:
        if workflow_id <= 0:
            raise ValidationError(detail="Invalid workflow_id")

        await validate_leave_approval_exists(db, workflow_id, request_id)

        query = select(LeaveApprovalWorkflow).where(
            LeaveApprovalWorkflow.workflow_id == workflow_id,
            LeaveApprovalWorkflow.is_active.is_(True),
            LeaveApprovalWorkflow.deleted_at.is_(None)
        )
        result = await db.execute(query)
        approval = result.scalar_one_or_none()
        if not approval:
            raise LeaveApprovalWorkflowError(workflow_id=workflow_id)

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db, request_id)
        if not any(p == Permission.MANAGE_LEAVE.value for p in user_permissions) and approval.approver_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this leave approval"
            )

        update_dict = update_data.model_dump(exclude_none=True)
        if not update_dict:
            raise ValidationError(detail="No fields provided for update")

        # Validate status if provided
        if "status" in update_dict and update_dict["status"] not in [LeaveRequestStatus.APPROVED, LeaveRequestStatus.REJECTED, LeaveRequestStatus.UNDER_REVIEW]:
            raise ValidationError(detail="Invalid status for leave approval")

        # Validate workflow progression and leave balance if status is updated
        if "status" in update_dict and update_dict["status"] in [LeaveRequestStatus.APPROVED, LeaveRequestStatus.REJECTED]:
            await validate_workflow_progression(db, approval.leave_id, approval.level, request_id)
            query = select(LeaveRequests).where(
                LeaveRequests.leave_id == approval.leave_id,
                LeaveRequests.is_active.is_(True),
                LeaveRequests.deleted_at.is_(None)
            )
            result = await db.execute(query)
            leave_request = result.scalar_one_or_none()
            if not leave_request:
                raise LeaveRequestNotFoundError(leave_id=approval.leave_id)
            if update_dict["status"] == LeaveRequestStatus.APPROVED:
                await validate_no_overlapping_leave_requests(
                    db, leave_request.user_id, leave_request.start_date, leave_request.end_date, approval.leave_id, request_id, settings
                )
                query_balance = select(LeaveBalances).where(
                    LeaveBalances.user_id == leave_request.user_id,
                    LeaveBalances.leave_type == leave_request.leave_type,
                    LeaveBalances.is_active.is_(True),
                    LeaveBalances.deleted_at.is_(None)
                )
                result_balance = await db.execute(query_balance)
                leave_balance = result_balance.scalar_one_or_none()
                if not leave_balance:
                    raise LeaveBalanceNotFoundError(user_id=leave_request.user_id, leave_type=leave_request.leave_type)
                available_days = leave_balance.allocated_days - leave_balance.used_days + leave_balance.carried_forward
                if leave_request.days_requested > available_days:
                    raise ValidationError(detail=f"Insufficient leave balance: {available_days} days available, {leave_request.days_requested} days requested")
                query_policy = select(LeavePolicies).where(
                    LeavePolicies.leave_type == leave_request.leave_type,
                    LeavePolicies.is_active.is_(True),
                    LeavePolicies.deleted_at.is_(None)
                )
                result_policy = await db.execute(query_policy)
                leave_policy = result_policy.scalar_one_or_none()
                if leave_policy and leave_request.days_requested > leave_policy.max_days:
                    raise ValidationError(detail=f"Requested days ({leave_request.days_requested}) exceed policy limit ({leave_policy.max_days}) for {leave_request.leave_type.value}")

        old_values = approval.__dict__.copy()
        for key, value in update_dict.items():
            setattr(approval, key, value)
        if "status" in update_dict:
            approval.action_taken_at = datetime.now(timezone.utc)
        approval.updated_at = datetime.now(timezone.utc)
        db.add(approval)

        # Update leave request if status is updated
        if "status" in update_dict:
            query = select(LeaveRequests).where(
                LeaveRequests.leave_id == approval.leave_id,
                LeaveRequests.is_active.is_(True),
                LeaveRequests.deleted_at.is_(None)
            )
            result = await db.execute(query)
            leave_request = result.scalar_one_or_none()
            if not leave_request:
                raise LeaveRequestNotFoundError(leave_id=approval.leave_id)
            leave_request.status = update_dict["status"]
            leave_request.approved_by = approval.approver_id
            leave_request.approved_at = datetime.now(timezone.utc)
            leave_request.updated_at = datetime.now(timezone.utc)
            db.add(leave_request)
            if update_dict["status"] == LeaveRequestStatus.APPROVED:
                leave_balance.used_days += leave_request.days_requested
                leave_balance.updated_at = datetime.now(timezone.utc)
                db.add(leave_balance)

        await db.commit()
        await db.refresh(approval)

        # Notify employee, manager, and admins if status updated
        query_lr = select(LeaveRequests).where(
            LeaveRequests.leave_id == approval.leave_id,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result_lr = await db.execute(query_lr)
        leave_request = result_lr.scalar_one_or_none()
        if "status" in update_dict:
            eat_tz = ZoneInfo("Africa/Nairobi")
            current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
            recipients = []
            query_employee = select(Users).where(
                Users.user_id == leave_request.user_id,
                Users.is_active.is_(True),
                Users.deleted_at.is_(None)
            )
            result_employee = await db.execute(query_employee)
            employee = result_employee.scalar_one_or_none()
            if employee:
                recipients.append((employee.email, employee.first_name))
            query_manager = select(Users).join(
                EmployeeHierarchy,
                and_(
                    EmployeeHierarchy.supervisor_id == Users.user_id,
                    EmployeeHierarchy.is_active.is_(True),
                    EmployeeHierarchy.deleted_at.is_(None)
                )
            ).where(
                EmployeeHierarchy.employee_id == leave_request.user_id,
                Users.is_active.is_(True),
                Users.deleted_at.is_(None)
            )
            result_manager = await db.execute(query_manager)
            manager = result_manager.scalar_one_or_none()
            if manager:
                recipients.append((manager.email, manager.first_name))
            admins = await get_user_permissions(Permission.MANAGE_LEAVE, db)
            recipients.extend([(admin.email, admin.first_name) for admin in admins])
            for email, first_name in recipients:
                await send_email(
                    to_email=email,
                    subject=f"Leave Approval Updated (ID: {workflow_id})",
                    body=(
                        f"Dear {first_name},\n\n"
                        f"The leave approval (ID: {workflow_id}) for leave request (ID: {leave_request.leave_id}) has been updated.\n"
                        f"Details:\n"
                        f"Leave Type: {leave_request.leave_type.value.capitalize()}\n"
                        f"Start Date: {leave_request.start_date}\n"
                        f"End Date: {leave_request.end_date}\n"
                        f"Days Requested: {leave_request.days_requested}\n"
                        f"Status: {update_dict['status'].value.capitalize()}\n"
                        f"Comments: {update_dict.get('comments', approval.comments) or 'None'}\n"
                        f"Updated At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                        f"Please review in the Employee Management System.\n\n"
                        f"Best regards,\nEmployee Management System"
                    ),
                    request_id=request_id
                )

        # Invalidate cache
        invalidate_user_cache(leave_request.user_id)
        await invalidate_cache_prefix("leave_approval_workflow")
        await invalidate_cache_prefix("leave_requests")
        logger.info(f"Cache invalidated for leave_approval_workflow, leave_requests, and user_id: {leave_request.user_id}", extra={"request_id": request_id})

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_LEAVE_APPROVAL,
            table_affected="leave_approval_workflow",
            record_id=workflow_id,
            old_values=old_values,
            new_values=approval.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Leave approval updated, workflow_id: {workflow_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return LeaveApprovalWorkflowOut.model_validate(approval)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (LeaveApprovalWorkflowError, LeaveRequestNotFoundError, LeaveBalanceNotFoundError) as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Forbidden access to update leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating leave approval")

async def delete_leave_approval(
    workflow_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.MANAGE_LEAVE]))
) -> None:
    """Soft delete a leave approval workflow entry with logging and notification."""
    try:
        if workflow_id <= 0:
            raise ValidationError(detail="Invalid workflow_id")

        await validate_leave_approval_exists(db, workflow_id, request_id)

        query = select(LeaveApprovalWorkflow).where(
            LeaveApprovalWorkflow.workflow_id == workflow_id,
            LeaveApprovalWorkflow.is_active.is_(True),
            LeaveApprovalWorkflow.deleted_at.is_(None)
        )
        result = await db.execute(query)
        approval = result.scalar_one_or_none()
        if not approval:
            raise LeaveApprovalWorkflowError(workflow_id=workflow_id)

        # Prevent deletion of approved workflows if configured
        if settings.PREVENT_DELETE_APPROVED_WORKFLOW and approval.status == LeaveRequestStatus.APPROVED:
            raise ValidationError(detail="Cannot delete approved leave approval workflow")

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db, request_id)
        if not any(p == Permission.MANAGE_LEAVE.value for p in user_permissions) and approval.approver_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this leave approval"
            )

        approval.is_active = False
        approval.deleted_at = datetime.now(timezone.utc)
        approval.updated_at = datetime.now(timezone.utc)
        db.add(approval)

        # Update leave request status if necessary
        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == approval.leave_id,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result = await db.execute(query)
        leave_request = result.scalar_one_or_none()
        if leave_request:
            query_remaining = select(LeaveApprovalWorkflow).where(
                LeaveApprovalWorkflow.leave_id == approval.leave_id,
                LeaveApprovalWorkflow.is_active.is_(True),
                LeaveApprovalWorkflow.deleted_at.is_(None)
            )
            result_remaining = await db.execute(query_remaining)
            if not result_remaining.scalars().first():
                leave_request.status = LeaveRequestStatus.UNDER_REVIEW
                leave_request.approved_by = None
                leave_request.approved_at = None
                leave_request.updated_at = datetime.now(timezone.utc)
                db.add(leave_request)

        await db.commit()

        # Notify employee, manager, and admins
        eat_tz = ZoneInfo("Africa/Nairobi")
        current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
        recipients = []
        query_employee = select(Users).where(
            Users.user_id == leave_request.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_employee = await db.execute(query_employee)
        employee = result_employee.scalar_one_or_none()
        if employee:
            recipients.append((employee.email, employee.first_name))
        query_manager = select(Users).join(
            EmployeeHierarchy,
            and_(
                EmployeeHierarchy.supervisor_id == Users.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
        ).where(
            EmployeeHierarchy.employee_id == leave_request.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_manager = await db.execute(query_manager)
        manager = result_manager.scalar_one_or_none()
        if manager:
            recipients.append((manager.email, manager.first_name))
        admins = await get_user_permissions(Permission.MANAGE_LEAVE, db)
        recipients.extend([(admin.email, admin.first_name) for admin in admins])
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"Leave Approval Deleted (ID: {workflow_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"The leave approval (ID: {workflow_id}) for leave request (ID: {leave_request.leave_id}) has been deleted.\n"
                    f"Details:\n"
                    f"Leave Type: {leave_request.leave_type.value.capitalize()}\n"
                    f"Start Date: {leave_request.start_date}\n"
                    f"End Date: {leave_request.end_date}\n"
                    f"Days Requested: {leave_request.days_requested}\n"
                    f"Deleted At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        # Invalidate cache
        invalidate_user_cache(leave_request.user_id)
        await invalidate_cache_prefix("leave_approval_workflow")
        await invalidate_cache_prefix("leave_requests")
        logger.info(f"Cache invalidated for leave_approval_workflow, leave_requests, and user_id: {leave_request.user_id}", extra={"request_id": request_id})

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_LEAVE_APPROVAL,
            table_affected="leave_approval_workflow",
            record_id=workflow_id,
            old_values=approval.__dict__,
            new_values=None,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Leave approval soft deleted, workflow_id: {workflow_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except LeaveApprovalWorkflowError as e:
        logger.error(f"Leave approval not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Forbidden access to delete leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting leave approval")

async def define_workflow_steps(
    workflow_steps: List[WorkflowStepCreate],
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.MANAGE_WORKFLOWS]))
) -> List[WorkflowStepOut]:
    """Define leave approval workflow steps with validation and logging."""
    try:
        if not workflow_steps:
            raise ValidationError(detail="At least one workflow step is required")
        if len(workflow_steps) > settings.MAX_WORKFLOW_LEVELS:
            raise ValidationError(detail=f"Cannot define more than {settings.MAX_WORKFLOW_LEVELS} workflow steps")

        leave_id = workflow_steps[0].leave_id
        await validate_leave_request_exists(db, leave_id, request_id)
        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == leave_id,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result = await db.execute(query)
        leave_request = result.scalar_one_or_none()
        if not leave_request:
            raise LeaveRequestNotFoundError(leave_id=leave_id)

        # Validate approvers and levels
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

        levels = set()
        for step in workflow_steps:
            if step.leave_id <= 0 or step.approver_id <= 0:
                raise ValidationError(detail="Invalid leave_id or approver_id")
            if step.level < 1 or step.level > settings.MAX_WORKFLOW_LEVELS:
                raise ValidationError(detail=f"Invalid level {step.level} for workflow step")
            if step.leave_id != leave_id:
                raise ValidationError(detail="All steps must belong to the same leave request")
            if step.approver_id not in users:
                raise UserNotFoundError(user_id=step.approver_id)
            if step.level in levels:
                raise ValidationError(detail=f"Duplicate level {step.level} for leave_id {leave_id}")
            levels.add(step.level)
            user_permissions = await get_user_permissions(step.approver_id, db, request_id)
            if Permission.APPROVE_LEAVE.value not in user_permissions:
                raise ValidationError(detail=f"Approver {step.approver_id} lacks APPROVE_LEAVE permission")

        created_steps = []
        for step in workflow_steps:
            db_step = LeaveApprovalWorkflow(
                leave_id=step.leave_id,
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

        # Notify employee, manager, approvers, and admins
        eat_tz = ZoneInfo("Africa/Nairobi")
        current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
        recipients = [(users[step.approver_id].email, users[step.approver_id].first_name) for step in workflow_steps]
        query_employee = select(Users).where(
            Users.user_id == leave_request.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_employee = await db.execute(query_employee)
        employee = result_employee.scalar_one_or_none()
        if employee:
            recipients.append((employee.email, employee.first_name))
        query_manager = select(Users).join(
            EmployeeHierarchy,
            and_(
                EmployeeHierarchy.supervisor_id == Users.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
        ).where(
            EmployeeHierarchy.employee_id == leave_request.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_manager = await db.execute(query_manager)
        manager = result_manager.scalar_one_or_none()
        if manager:
            recipients.append((manager.email, manager.first_name))
        admins = await get_user_permissions(Permission.MANAGE_LEAVE, db)
        recipients.extend([(admin.email, admin.first_name) for admin in admins])
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"New Workflow Steps Defined for Leave Request (ID: {leave_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"New workflow steps have been defined for leave request (ID: {leave_id}) for user ID {leave_request.user_id}.\n"
                    f"Details:\n"
                    f"Leave Type: {leave_request.leave_type.value.capitalize()}\n"
                    f"Start Date: {leave_request.start_date}\n"
                    f"End Date: {leave_request.end_date}\n"
                    f"Days Requested: {leave_request.days_requested}\n"
                    f"Created At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        # Invalidate cache
        invalidate_user_cache(leave_request.user_id)
        await invalidate_cache_prefix("leave_approval_workflow")
        await invalidate_cache_prefix("leave_requests")
        logger.info(f"Cache invalidated for leave_approval_workflow, leave_requests, and user_id: {leave_request.user_id}", extra={"request_id": request_id})

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DEFINE_WORKFLOW,
            table_affected="leave_approval_workflow",
            record_id=None,
            old_values=None,
            new_values={f"step_{i}": step.__dict__ for i, step in enumerate(created_steps)},
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Defined {len(created_steps)} workflow steps for leave_id: {leave_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [WorkflowStepOut.model_validate(step) for step in created_steps]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (UserNotFoundError, LeaveRequestNotFoundError) as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error defining workflow steps: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error defining workflow steps")

async def get_workflow_by_type(
    leave_type: LeaveType,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_WORKFLOWS]))
) -> List[WorkflowStepOut]:
    """Retrieve workflow steps for a specific leave type with authorization checks and caching."""
    try:
        if leave_type not in LeaveType:
            raise ValidationError(detail=f"Invalid leave type: {leave_type}")

        cache_key = f"workflow_by_type:{leave_type}"
        cached_steps = await get_cache(cache_key)
        if cached_steps:
            logger.info(f"Cache hit for workflow_by_type:{leave_type}", extra={"request_id": request_id})
            return [WorkflowStepOut(**step) for step in cached_steps]

        query = select(LeaveRequests).where(
            LeaveRequests.leave_type == leave_type,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result = await db.execute(query)
        leave_requests = result.scalars().all()
        if not leave_requests:
            return []

        leave_ids = [lr.leave_id for lr in leave_requests]
        query = select(LeaveApprovalWorkflow).where(
            LeaveApprovalWorkflow.leave_id.in_(leave_ids),
            LeaveApprovalWorkflow.is_active.is_(True),
            LeaveApprovalWorkflow.deleted_at.is_(None)
        ).order_by(LeaveApprovalWorkflow.created_at.desc())
        result = await db.execute(query)
        steps = result.scalars().all()

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db, request_id)
        if not any(p in [Permission.VIEW_WORKFLOWS.value, Permission.MANAGE_LEAVE.value] for p in user_permissions):
            allowed_leave_ids = []
            for lr in leave_requests:
                if lr.user_id == current_user.user_id:
                    allowed_leave_ids.append(lr.leave_id)
                else:
                    query_hierarchy = select(EmployeeHierarchy).where(
                        EmployeeHierarchy.employee_id == lr.user_id,
                        EmployeeHierarchy.supervisor_id == current_user.user_id,
                        EmployeeHierarchy.is_active.is_(True),
                        EmployeeHierarchy.deleted_at.is_(None)
                    )
                    result_hierarchy = await db.execute(query_hierarchy)
                    if result_hierarchy.scalar_one_or_none():
                        allowed_leave_ids.append(lr.leave_id)
                    else:
                        query_approver = select(LeaveApprovalWorkflow).where(
                            LeaveApprovalWorkflow.leave_id == lr.leave_id,
                            LeaveApprovalWorkflow.approver_id == current_user.user_id,
                            LeaveApprovalWorkflow.is_active.is_(True),
                            LeaveApprovalWorkflow.deleted_at.is_(None)
                        )
                        result_approver = await db.execute(query_approver)
                        if result_approver.scalar_one_or_none():
                            allowed_leave_ids.append(lr.leave_id)
            steps = [step for step in steps if step.leave_id in allowed_leave_ids]

        steps_dict = [WorkflowStepOut.model_validate(step).model_dump() for step in steps]
        await set_cache(cache_key, steps_dict, ttl=300)
        logger.info(f"Cache set for workflow_by_type:{leave_type}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(steps)} workflow steps for leave_type: {leave_type}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [WorkflowStepOut.model_validate(step) for step in steps]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving workflow steps for leave_type {leave_type}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving workflow steps")