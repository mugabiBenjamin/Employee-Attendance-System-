from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.leave_balances import LeaveBalances
from app.models.leave_policies import LeavePolicies
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.schemas.leave_balance import LeaveBalanceOut
from app.core.enums import SystemAction, Permission
from app.core.exceptions import LeaveBalanceNotFoundError, UserNotFoundError, LeavePolicyNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

async def get_leave_balances_by_user_and_type(
    user_id: int,
    leave_type: Optional[str] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.VIEW_LEAVE_BALANCE, Permission.VIEW_OWN_LEAVE_BALANCE]))
) -> List[LeaveBalanceOut]:
    """Retrieve leave balances for a user with optional leave type filter."""
    try:
        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise UserNotFoundError(user_id=user_id)

        if not any(p in current_user.permissions for p in [Permission.VIEW_LEAVE_BALANCE, Permission.MANAGE_LEAVE]) and user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view leave balances for this user"
            )

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
                LeavePolicies.deleted_at.is_(None)
            )
            result = await db.execute(query)
            policy = result.scalar_one_or_none()
            balance_data = LeaveBalanceOut.model_validate(balance)
            balance_data.policy_details = policy.__dict__ if policy else {}
            balance_out.append(balance_data)

        logger.info(f"Retrieved {len(balance_out)} leave balances for user_id: {user_id}")
        return balance_out

    except (UserNotFoundError, LeaveBalanceNotFoundError):
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving leave balances for user_id {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving leave balances"
        )

async def update_leave_balance(
    request: Request,
    user_id: int,
    leave_type: str,
    balance_change: float,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.UPDATE_LEAVE_BALANCE]))
) -> LeaveBalanceOut:
    """Update leave balance for a user with validation and logging."""
    try:
        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise UserNotFoundError(user_id=user_id)

        query = select(LeavePolicies).where(
            LeavePolicies.leave_type == leave_type,
            LeavePolicies.is_active.is_(True),
            LeavePolicies.deleted_at.is_(None)
        )
        result = await db.execute(query)
        policy = result.scalar_one_or_none()
        if not policy:
            raise LeavePolicyNotFoundError(leave_type=leave_type)

        query = select(LeaveBalances).where(
            LeaveBalances.user_id == user_id,
            LeaveBalances.leave_type == leave_type,
            LeaveBalances.is_active.is_(True),
            LeaveBalances.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_balance = result.scalar_one_or_none()

        if not db_balance:
            db_balance = LeaveBalances(
                user_id=user_id,
                leave_type=leave_type,
                allocated_days=0,
                used_days=0,
                carried_forward=0,
                year=datetime.now(timezone.utc).year,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )

        old_values = db_balance.__dict__.copy()
        new_used_days = max(0.0, db_balance.used_days - balance_change)
        db_balance.used_days = new_used_days
        db_balance.updated_at = datetime.now(timezone.utc)
        db.add(db_balance)
        await db.commit()
        await db.refresh(db_balance)

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_LEAVE_BALANCE,
            table_affected="leave_balances",
            record_id=db_balance.balance_id,
            old_values=old_values,
            new_values=db_balance.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        balance_out = LeaveBalanceOut.model_validate(db_balance)
        balance_out.policy_details = policy.__dict__ if policy else {}

        logger.info(f"Leave balance updated, balance_id: {db_balance.balance_id}, user_id: {user_id}, leave_type: {leave_type}")
        return balance_out

    except (UserNotFoundError, LeavePolicyNotFoundError):
        raise
    except Exception as e:
        logger.error(f"Error updating leave balance for user_id {user_id}, leave_type {leave_type}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating leave balance"
        )