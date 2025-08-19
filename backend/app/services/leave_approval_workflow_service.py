import ipaddress
from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.leave_approval_workflow import LeaveApprovalWorkflow
from app.models.leave_requests import LeaveRequests
from app.models.users import Users
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.leave_balances import LeaveBalances
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
from app.core.permissions import require_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_leave_request_exists
from app.core.utils import get_request_id, get_users_with_permission
from app.services.user_role_service import get_user_permissions
from app.services.system_log_service import create_system_log
import logging

logger = logging.getLogger(__name__)

async def validate_leave_approval_exists(db: AsyncSession, workflow_id: int, request_id: Optional[str] = None) -> None:
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

        # Validate hierarchy or MANAGE_LEAVE permission
        user_permissions = await get_user_permissions(approval.approver_id, db, request_id)
        is_manager = False
        if approval.approver_id != current_user.user_id:
            query = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == leave_request.user_id,
                EmployeeHierarchy.manager_id == approval.approver_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result = await db.execute(query)
            is_manager = result.scalar_one_or_none() is not None
            if not is_manager and Permission.MANAGE_LEAVE not in user_permissions:
                raise ValidationError(detail="Approver is not in the employee's hierarchy or lacks MANAGE_LEAVE permission")

        # Validate permissions
        if Permission.APPROVE_LEAVE not in user_permissions and approval.approver_id != current_user.user_id:
            raise ValidationError(detail="Approver lacks APPROVE_LEAVE permission")

        # Validate status
        if approval.status not in [LeaveRequestStatus.APPROVED, LeaveRequestStatus.REJECTED]:
            raise ValidationError(detail="Invalid status for leave approval")

        # Validate workflow progression
        await validate_workflow_progression(db, approval.leave_id, approval.level, request_id)

        # Update leave balance if approved
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
            available_days = leave_balance.allocated_days - leave_balance.used_days + leave_balance.carried_forward
            if leave_request.days_requested > available_days:
                raise ValidationError(detail="Insufficient leave balance")
            leave_balance.used_days += leave_request.days_requested
            leave_balance.updated_at = datetime.now(timezone.utc)
            db.add(leave_balance)

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
        db.add(leave_request)
        await db.commit()
        await db.refresh(db_approval)

        # Invalidate cache
        await invalidate_cache_prefix("leave_approval_workflow")
        await invalidate_cache_prefix("leave_requests")
        logger.debug(f"Cache cleared for leave_approval_workflow and leave_requests")

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.APPROVE_LEAVE,
            table_affected="leave_approval_workflow",
            record_id=db_approval.workflow_id,
            old_values=None,
            new_values=db_approval.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        # Notify employee and admins
        query_user = select(Users).where(Users.user_id == leave_request.user_id)
        result_user = await db.execute(query_user)
        employee = result_user.scalar_one_or_none()
        admins = await get_users_with_permission(Permission.MANAGE_LEAVE, db)
        recipients = [(employee.email, employee.first_name)] + [(admin.email, admin.first_name) for admin in admins]
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"Leave Request {approval.status.value.capitalize() if hasattr(approval.status, 'value') else str(approval.status).capitalize()} (ID: {approval.leave_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"The leave request (ID: {approval.leave_id}) from {leave_request.start_date} to {leave_request.end_date} "
                    f"has been {approval.status.value.lower() if hasattr(approval.status, 'value') else str(approval.status).lower()}.\n"
                    f"Comments: {approval.comments or 'None'}\n\n"
                    f"Please contact HR for any questions.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        logger.info(
            f"Leave approval processed, workflow_id: {db_approval.workflow_id}, leave_id: {approval.leave_id}, status: {approval.status}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return LeaveApprovalWorkflowOut.model_validate(db_approval)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except LeaveRequestNotFoundError as e:
        logger.error(f"Leave request not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except LeaveBalanceNotFoundError as e:
        logger.error(f"Leave balance not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error processing leave approval: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error processing leave approval: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

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
        if not any(p in user_permissions for p in [Permission.VIEW_LEAVE_APPROVAL, Permission.MANAGE_LEAVE]) and approval.approver_id != current_user.user_id:
            query = select(LeaveRequests).where(
                LeaveRequests.leave_id == approval.leave_id,
                LeaveRequests.user_id == current_user.user_id,
                LeaveRequests.is_active.is_(True),
                LeaveRequests.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view this leave approval"
                )

        approval_dict = LeaveApprovalWorkflowOut.model_validate(approval).model_dump()
        await set_cache(cache_key, approval_dict, ttl=300)

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
    except DatabaseError as e:
        logger.error(f"Database error retrieving leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

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
            return [LeaveApprovalWorkflowOut(**approval) for approval in cached_approvals]

        # Validate leave request
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
            LeaveApprovalWorkflow.leave_id == leave_id,
            LeaveApprovalWorkflow.is_active.is_(True),
            LeaveApprovalWorkflow.deleted_at.is_(None)
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        approvals = result.scalars().all()

        approvals_dict = [LeaveApprovalWorkflowOut.model_validate(approval).model_dump() for approval in approvals]
        await set_cache(cache_key, approvals_dict, ttl=300)

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
    except DatabaseError as e:
        logger.error(f"Database error retrieving leave approvals for leave_id {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave approvals for leave_id {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

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
        if not any(p in user_permissions for p in [Permission.MANAGE_LEAVE]) and approval.approver_id != current_user.user_id:
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

        # Validate workflow progression if status is updated
        if "status" in update_dict and update_dict["status"] in [LeaveRequestStatus.APPROVED, LeaveRequestStatus.REJECTED]:
            await validate_workflow_progression(db, approval.leave_id, approval.level, request_id)

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

            # Update leave balance if approved
            if update_dict["status"] == LeaveRequestStatus.APPROVED:
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
                    raise ValidationError(detail="Insufficient leave balance")
                leave_balance.used_days += leave_request.days_requested
                leave_balance.updated_at = datetime.now(timezone.utc)
                db.add(leave_balance)

        await db.commit()
        await db.refresh(approval)

        # Invalidate cache
        await invalidate_cache_prefix("leave_approval_workflow")
        await invalidate_cache_prefix("leave_requests")
        logger.debug(f"Cache cleared for leave_approval_workflow and leave_requests")

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

        # Notify employee and admins if status updated
        if "status" in update_dict:
            query_user = select(Users).where(Users.user_id == leave_request.user_id)
            result_user = await db.execute(query_user)
            employee = result_user.scalar_one_or_none()
            admins = await get_users_with_permission(Permission.MANAGE_LEAVE, db)
            recipients = [(employee.email, employee.first_name)] + [(admin.email, admin.first_name) for admin in admins]
            for email, first_name in recipients:
                await send_email(
                    to_email=email,
                    subject=f"Leave Approval Updated (ID: {workflow_id})",
                    body=(
                        f"Dear {first_name},\n\n"
                        f"The leave approval (ID: {workflow_id}) for leave request (ID: {approval.leave_id}) "
                        f"has been updated to {update_dict['status'].value.lower() if hasattr(update_dict['status'], 'value') else str(update_dict['status']).lower()}.\n"
                        f"Comments: {update_dict.get('comments', 'None')}\n\n"
                        f"Please contact HR for any questions.\n\n"
                        f"Best regards,\nEmployee Management System"
                    ),
                    request_id=request_id
                )

        logger.info(
            f"Leave approval updated, workflow_id: {workflow_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return LeaveApprovalWorkflowOut.model_validate(approval)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except LeaveApprovalWorkflowError as e:
        logger.error(f"Leave approval not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except LeaveRequestNotFoundError as e:
        logger.error(f"Leave request not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except LeaveBalanceNotFoundError as e:
        logger.error(f"Leave balance not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Forbidden access to update leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except DatabaseError as e:
        logger.error(f"Database error updating leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error updating leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

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

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db, request_id)
        if not any(p in user_permissions for p in [Permission.MANAGE_LEAVE]) and approval.approver_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this leave approval"
            )

        approval.is_active = False
        approval.deleted_at = datetime.now(timezone.utc)
        approval.updated_at = datetime.now(timezone.utc)
        db.add(approval)
        await db.commit()

        # Invalidate cache
        await invalidate_cache_prefix("leave_approval_workflow")
        await invalidate_cache_prefix("leave_requests")
        logger.debug(f"Cache cleared for leave_approval_workflow and leave_requests")

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

        # Notify employee and admins
        query_lr = select(LeaveRequests).where(
            LeaveRequests.leave_id == approval.leave_id,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result_lr = await db.execute(query_lr)
        leave_request = result_lr.scalar_one_or_none()
        query_user = select(Users).where(Users.user_id == leave_request.user_id)
        result_user = await db.execute(query_user)
        employee = result_user.scalar_one_or_none()
        admins = await get_users_with_permission(Permission.MANAGE_LEAVE, db)
        recipients = [(employee.email, employee.first_name)] + [(admin.email, admin.first_name) for admin in admins]
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"Leave Approval Deleted (ID: {workflow_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"The leave approval (ID: {workflow_id}) for leave request (ID: {approval.leave_id}) has been deleted.\n"
                    f"Please contact HR for any questions.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

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
    except DatabaseError as e:
        logger.error(f"Database error deleting leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error deleting leave approval {workflow_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

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

        # Validate leave request
        leave_id = workflow_steps[0].leave_id
        await validate_leave_request_exists(db, leave_id, request_id)

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
        levels = set()
        created_steps = []
        for step in workflow_steps:
            if step.level < 1 or step.level > 5:
                raise ValidationError(detail=f"Invalid level {step.level} for workflow step")
            if step.leave_id != leave_id:
                raise ValidationError(detail="All steps must belong to the same leave request")
            if step.approver_id not in users:
                raise UserNotFoundError(user_id=step.approver_id)
            if step.level in levels:
                raise ValidationError(detail=f"Duplicate level {step.level} for leave_id {leave_id}")
            levels.add(step.level)
            user_permissions = await get_user_permissions(step.approver_id, db, request_id)
            if Permission.APPROVE_LEAVE not in user_permissions:
                raise ValidationError(detail=f"Approver {step.approver_id} lacks APPROVE_LEAVE permission")

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

        # Invalidate cache
        await invalidate_cache_prefix("leave_approval_workflow")
        await invalidate_cache_prefix("leave_requests")
        logger.debug(f"Cache cleared for leave_approval_workflow and leave_requests")

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DEFINE_WORKFLOW,
            table_affected="leave_approval_workflow",
            record_id=None,
            old_values=None,
            new_values={f"step_{i}": step.__dict__ for i, step in enumerate(created_steps)},
            ip_address=ipaddress.ip_address(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        # Notify approvers and admins
        admins = await get_users_with_permission(Permission.MANAGE_LEAVE, db)
        recipients = [(users[step.approver_id].email, users[step.approver_id].first_name) for step in workflow_steps]
        recipients += [(admin.email, admin.first_name) for admin in admins]
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"New Workflow Steps Defined for Leave Request (ID: {leave_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"New workflow steps have been defined for leave request (ID: {leave_id}).\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

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
    leave_type: LeaveType,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_WORKFLOWS]))
) -> List[WorkflowStepOut]:
    """Retrieve workflow steps for a specific leave type with authorization checks and caching."""
    try:
        cache_key = f"workflow_by_type:{leave_type}"
        cached_steps = await get_cache(cache_key)
        if cached_steps:
            return [WorkflowStepOut(**step) for step in cached_steps]

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

        steps_dict = [WorkflowStepOut.model_validate(step).model_dump() for step in steps]
        await set_cache(cache_key, steps_dict, ttl=300)

        logger.info(
            f"Retrieved {len(steps)} workflow steps for leave_type: {leave_type}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [WorkflowStepOut.model_validate(step) for step in steps]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error retrieving workflow steps for leave_type {leave_type}: {str(e)}", extra={"request_id": request_id})
        raise
    except DatabaseError as e:
        logger.error(f"Database error retrieving workflow steps for leave_type {leave_type}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving workflow steps for leave_type {leave_type}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")