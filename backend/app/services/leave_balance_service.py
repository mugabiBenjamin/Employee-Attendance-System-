from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from datetime import datetime, timezone
from app.models.leave_balances import LeaveBalances
from app.models.leave_policies import LeavePolicies
from app.models.users import Users
from app.models.leave_requests import LeaveRequests
from app.schemas.leave_balance import LeaveBalanceOut, LeavePolicyDetails
from app.schemas.system_log import SystemLogCreate
from app.core.config import Settings, get_settings
from app.core.enums import LeaveType, SystemAction, Permission, LeaveRequestStatus
from app.core.mail import send_email
from app.core.exceptions import LeaveBalanceNotFoundError, UserNotFoundError, LeavePolicyNotFoundError, ValidationError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_user_exists, validate_leave_policy_exists
from app.services.system_log_service import create_system_log
import logging

logger = logging.getLogger(__name__)

def get_request_id(request: Request) -> Optional[str]:
    """Extract request_id from the request state."""
    return request.state.request_id if hasattr(request.state, "request_id") else None

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

        user_permissions = current_user.permissions
        if not any(p in user_permissions for p in [Permission.VIEW_LEAVE_BALANCE, Permission.MANAGE_LEAVE]) and user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view leave balances for this user"
            )

        cache_key = f"leave_balances:{user_id}:{leave_type or 'all'}"
        cached_balances = await get_cache(cache_key)
        if cached_balances:
            return [LeaveBalanceOut(**balance) for balance in cached_balances]

        query = select(LeaveBalances).where(
            LeaveBalances.user_id == user_id,
            LeaveBalances.is_active.is_(True),
            LeaveBalances.deleted_at.is_(None)
        )
        if leave_type:
            query = query.where(LeaveBalances.leave_type == leave_type)

        result = await db.execute(query)
        balances = result.scalars().all()

        if not balances:
            raise LeaveBalanceNotFoundError(user_id=user_id, leave_type=leave_type or "any")

        balance_out = []
        for balance in balances:
            query = select(LeavePolicies).where(
                LeavePolicies.leave_type == balance.leave_type,
                LeavePolicies.is_active.is_(True),
                LeavePolicies.deleted_at.is_(None),
                LeavePolicies.effective_from <= datetime.now(timezone.utc).date(),
                or_(LeavePolicies.effective_to.is_(None), LeavePolicies.effective_to >= datetime.now(timezone.utc).date())
            )
            result = await db.execute(query)
            policy = result.scalar_one_or_none()
            balance_data = LeaveBalanceOut.model_validate(balance)
            balance_data.policy_details = LeavePolicyDetails.model_validate(policy) if policy else LeavePolicyDetails()
            balance_out.append(balance_data)

        balances_dict = [balance.model_dump() for balance in balance_out]
        await set_cache(cache_key, balances_dict, ttl=300)

        logger.info(
            f"Retrieved {len(balance_out)} leave balances for user_id: {user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return balance_out

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (UserNotFoundError, LeaveBalanceNotFoundError) as e:
        logger.error(f"Error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Forbidden access to leave balances for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Error retrieving leave balances for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
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
        if abs(balance_change) > 365:
            raise ValidationError(detail="Balance change must be reasonable (within 365 days)")

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
            raise ValidationError(detail="Version mismatch, balance has been updated by another user")

        # Check for pending leave requests
        query = select(LeaveRequests).where(
            LeaveRequests.user_id == user_id,
            LeaveRequests.leave_type == leave_type,
            LeaveRequests.status.in_([LeaveRequestStatus.UNDER_REVIEW, LeaveRequestStatus.APPROVED]),
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result = await db.execute(query)
        pending_requests = result.scalars().all()
        if pending_requests and balance_change < 0:
            total_pending_days = sum((req.end_date - req.start_date).days + 1 for req in pending_requests)
            if db_balance.allocated_days + db_balance.carried_forward - db_balance.used_days - total_pending_days + balance_change < 0:
                raise ValidationError(detail="Balance change would result in negative balance due to pending requests")

        old_values = db_balance.__dict__.copy()
        new_used_days = max(0.0, float(db_balance.used_days) - balance_change)
        available_balance = float(db_balance.allocated_days) + float(db_balance.carried_forward) - new_used_days
        if available_balance < 0:
            raise ValidationError(detail="Balance change would result in negative balance")

        db_balance.used_days = new_used_days
        db_balance.version += 1
        db_balance.updated_at = datetime.now(timezone.utc)
        db.add(db_balance)
        await db.commit()
        await db.refresh(db_balance)

        # Invalidate cache
        await invalidate_cache_prefix(f"leave_balances:{user_id}")
        logger.debug(f"Cache cleared for leave_balances:{user_id}")

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

        # Notify admins
        query_admins = select(Users).where(Users.has_role(Permission.MANAGE_LEAVE))
        result_admins = await db.execute(query_admins)
        admins = result_admins.scalars().all()
        for admin in admins:
            await send_email(
                to_email=admin.email,
                subject=f"Leave Balance Updated (ID: {db_balance.balance_id})",
                body=(
                    f"Dear {admin.first_name},\n\n"
                    f"The leave balance (ID: {db_balance.balance_id}) for user ID {user_id} and {leave_type} "
                    f"has been updated to version {db_balance.version}.\n"
                    f"New used days: {db_balance.used_days}.\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        # Fetch policy details
        query = select(LeavePolicies).where(
            LeavePolicies.leave_type == db_balance.leave_type,
            LeavePolicies.is_active.is_(True),
            LeavePolicies.deleted_at.is_(None),
            LeavePolicies.effective_from <= datetime.now(timezone.utc).date(),
            or_(LeavePolicies.effective_to.is_(None), LeavePolicies.effective_to >= datetime.now(timezone.utc).date())
        )
        result = await db.execute(query)
        policy = result.scalar_one_or_none()
        balance_out = LeaveBalanceOut.model_validate(db_balance)
        balance_out.policy_details = LeavePolicyDetails.model_validate(policy) if policy else LeavePolicyDetails()

        logger.info(
            f"Leave balance updated, balance_id: {db_balance.balance_id}, user_id: {user_id}, leave_type: {leave_type}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return balance_out

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (UserNotFoundError, LeavePolicyNotFoundError, LeaveBalanceNotFoundError) as e:
        logger.error(f"Error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating leave balance for user_id {user_id}, leave_type {leave_type}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating leave balance")