from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.models.leave_balances import LeaveBalances
from app.models.leave_policies import LeavePolicies
from app.models.users import Users
from app.models.leave_requests import LeaveRequests
from app.models.employee_hierarchy import EmployeeHierarchy
from app.schemas.leave_balance import LeaveBalanceOut, LeavePolicyDetails
from app.schemas.system_log import SystemLogCreate
from app.core.config import Settings, get_settings
from app.core.enums import LeaveType, SystemAction, Permission, LeaveRequestStatus
from app.core.mail import send_email
from app.core.exceptions import LeaveBalanceNotFoundError, UserNotFoundError, LeavePolicyNotFoundError, ValidationError
from app.core.security import get_current_user
from app.core.permissions import require_permissions, invalidate_user_cache, get_user_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_user_exists, validate_leave_policy_exists
from app.core.utils import get_request_id
from app.services.system_log_service import create_system_log
import logging

logger = logging.getLogger(__name__)

async def get_leave_balances_by_user_and_type(
    user_id: int,
    leave_type: Optional[LeaveType] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_LEAVE_BALANCE, Permission.VIEW_OWN_LEAVE_BALANCE]))
) -> List[LeaveBalanceOut]:
    """Retrieve leave balances for a user with optional leave type filter and caching."""
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user_id")

        await validate_user_exists(db, user_id, request_id)

        user_permissions = await get_user_permissions(current_user.user_id, db, request_id)
        if not any(p in [Permission.VIEW_LEAVE_BALANCE.value, Permission.MANAGE_LEAVE.value] for p in user_permissions) and user_id != current_user.user_id:
            query_hierarchy = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == user_id,
                EmployeeHierarchy.supervisor_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result_hierarchy = await db.execute(query_hierarchy)
            if not result_hierarchy.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view leave balances for this user"
                )

        cache_key = f"leave_balances:{user_id}:{leave_type or 'all'}"
        cached_balances = await get_cache(cache_key)
        if cached_balances:
            logger.info(f"Cache hit for leave_balances:{user_id}:{leave_type or 'all'}", extra={"request_id": request_id})
            return [LeaveBalanceOut(**balance) for balance in cached_balances]

        query = select(LeaveBalances).where(
            LeaveBalances.user_id == user_id,
            LeaveBalances.is_active.is_(True),
            LeaveBalances.deleted_at.is_(None)
        )
        if leave_type:
            query = query.where(LeaveBalances.leave_type == leave_type)
        query = query.order_by(LeaveBalances.leave_type.asc())
        result = await db.execute(query)
        balances = result.scalars().all()

        if not balances:
            raise LeaveBalanceNotFoundError(user_id=user_id, leave_type=leave_type or "any")

        balance_out = []
        for balance in balances:
            query_policy = select(LeavePolicies).where(
                LeavePolicies.leave_type == balance.leave_type,
                LeavePolicies.is_active.is_(True),
                LeavePolicies.deleted_at.is_(None)
            )
            result_policy = await db.execute(query_policy)
            policy = result_policy.scalar_one_or_none()
            
            query_requests = select(LeaveRequests).where(
                LeaveRequests.user_id == user_id,
                LeaveRequests.leave_type == balance.leave_type,
                LeaveRequests.status.in_([LeaveRequestStatus.UNDER_REVIEW, LeaveRequestStatus.APPROVED]),
                LeaveRequests.is_active.is_(True),
                LeaveRequests.deleted_at.is_(None)
            )
            result_requests = await db.execute(query_requests)
            pending_requests = result_requests.scalars().all()
            pending_days = sum((req.end_date - req.start_date).days + 1 for req in pending_requests if req.start_date and req.end_date)
            
            balance_data = LeaveBalanceOut.model_validate(balance)
            balance_data.policy_details = LeavePolicyDetails.model_validate(policy) if policy else LeavePolicyDetails()
            balance_data.pending_days = pending_days
            balance_out.append(balance_data)

        balances_dict = [balance.model_dump() for balance in balance_out]
        await set_cache(cache_key, balances_dict, ttl=300)
        logger.info(f"Cache set for leave_balances:{user_id}:{leave_type or 'all'}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(balance_out)} leave balances for user_id: {user_id}, leave_type: {leave_type or 'all'}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return balance_out

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (UserNotFoundError, LeaveBalanceNotFoundError) as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Forbidden access to leave balances for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave balances for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave balances")

async def update_leave_balance(
    user_id: int,
    leave_type: LeaveType,
    balance_change: float,
    version: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.UPDATE_LEAVE_BALANCE]))
) -> LeaveBalanceOut:
    """Update leave balance for a user with validation, version control, and logging."""
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user_id")
        if version <= 0:
            raise ValidationError(detail="Invalid version")
        if leave_type not in LeaveType:
            raise ValidationError(detail=f"Invalid leave type: {leave_type}")
        if abs(balance_change) > settings.MAX_BALANCE_CHANGE:
            raise ValidationError(detail=f"Balance change must be within {settings.MAX_BALANCE_CHANGE} days")

        await validate_user_exists(db, user_id, request_id)
        await validate_leave_policy_exists(db, leave_type, request_id)

        query = select(LeaveBalances).where(
            LeaveBalances.user_id == user_id,
            LeaveBalances.leave_type == leave_type,
            LeaveBalances.is_active.is_(True),
            LeaveBalances.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_balance = result.scalar_one_or_none()

        if not db_balance:
            raise LeaveBalanceNotFoundError(user_id=user_id, leave_type=leave_type)

        if db_balance.version != version:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Version mismatch, balance has been updated by another user")

        # Validate against leave policy
        query_policy = select(LeavePolicies).where(
            LeavePolicies.leave_type == leave_type,
            LeavePolicies.is_active.is_(True),
            LeavePolicies.deleted_at.is_(None)
        )
        result_policy = await db.execute(query_policy)
        policy = result_policy.scalar_one_or_none()
        if not policy:
            raise LeavePolicyNotFoundError(leave_type=leave_type)
        if balance_change > 0:
            total_allocated = float(db_balance.allocated_days) + float(db_balance.carried_forward)
            if total_allocated + balance_change > policy.max_days:
                raise ValidationError(detail=f"Balance change would exceed policy limit of {policy.max_days} days for {leave_type.value}")

        # Check for pending and approved leave requests
        query_requests = select(LeaveRequests).where(
            LeaveRequests.user_id == user_id,
            LeaveRequests.leave_type == leave_type,
            LeaveRequests.status.in_([LeaveRequestStatus.UNDER_REVIEW, LeaveRequestStatus.APPROVED]),
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result_requests = await db.execute(query_requests)
        pending_requests = result_requests.scalars().all()
        total_pending_days = sum((req.end_date - req.start_date).days + 1 for req in pending_requests if req.start_date and req.end_date)

        if pending_requests and balance_change < 0:
            available_balance = float(db_balance.allocated_days) + float(db_balance.carried_forward) - float(db_balance.used_days)
            if available_balance - total_pending_days + balance_change < 0:
                raise ValidationError(detail="Balance change would result in negative balance due to pending or approved requests")

        # Validate no negative allocation if configured
        if settings.PREVENT_NEGATIVE_ALLOCATION:
            if float(db_balance.allocated_days) + balance_change < 0 or float(db_balance.carried_forward) + balance_change < 0:
                raise ValidationError(detail="Balance change would result in negative allocated or carried forward days")

        old_values = db_balance.__dict__.copy()
        new_used_days = max(0.0, float(db_balance.used_days) - balance_change)
        available_balance = float(db_balance.allocated_days) + float(db_balance.carried_forward) - new_used_days
        if available_balance < 0:
            raise ValidationError(detail=f"Balance change would result in negative available balance: {available_balance}")

        db_balance.used_days = new_used_days
        db_balance.version += 1
        db_balance.updated_at = datetime.now(timezone.utc)
        db.add(db_balance)
        await db.commit()
        await db.refresh(db_balance)

        # Notify employee, manager, and admins
        eat_tz = ZoneInfo("Africa/Nairobi")
        current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
        recipients = []
        query_employee = select(Users).where(
            Users.user_id == user_id,
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
            EmployeeHierarchy.employee_id == user_id,
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
                subject=f"Leave Balance Updated (ID: {db_balance.balance_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"The leave balance (ID: {db_balance.balance_id}) for user ID {user_id} has been updated.\n"
                    f"Details:\n"
                    f"Leave Type: {leave_type.value.capitalize()}\n"
                    f"Change: {'Added' if balance_change > 0 else 'Deducted'} {abs(balance_change)} days\n"
                    f"New Used Days: {db_balance.used_days}\n"
                    f"Available Balance: {float(db_balance.allocated_days) + float(db_balance.carried_forward) - float(db_balance.used_days)} days\n"
                    f"Updated At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        # Invalidate cache
        invalidate_user_cache(user_id)
        await invalidate_cache_prefix("leave_balances")
        logger.info(f"Cache invalidated for leave_balances and user_id: {user_id}", extra={"request_id": request_id})

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_LEAVE_BALANCE,
            table_affected="leave_balances",
            record_id=db_balance.balance_id,
            old_values=old_values,
            new_values=db_balance.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        balance_out = LeaveBalanceOut.model_validate(db_balance)
        balance_out.policy_details = LeavePolicyDetails.model_validate(policy) if policy else LeavePolicyDetails()
        balance_out.pending_days = total_pending_days

        logger.info(
            f"Leave balance updated, balance_id: {db_balance.balance_id}, user_id: {user_id}, leave_type: {leave_type}, change: {balance_change}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return balance_out

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (UserNotFoundError, LeavePolicyNotFoundError, LeaveBalanceNotFoundError) as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Conflict error updating leave balance for user_id {user_id}, leave_type {leave_type}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating leave balance for user_id {user_id}, leave_type {leave_type}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating leave balance")