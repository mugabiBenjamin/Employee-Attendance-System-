from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.enums import Permission
from app.services.leave_balance_service import (
    get_leave_balances_by_user_and_type,
    update_leave_balance
)
from app.schemas.leave_balance import LeaveBalanceOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leave-balances", tags=["Leave Balances"])

@router.get(
    "/{user_id}",
    response_model=List[LeaveBalanceOut],
    summary="Get leave balances by user and type",
    description="Retrieve leave balances for a specific user, optionally filtered by leave type."
)
@require_permissions([Permission.VIEW_LEAVE_BALANCE, Permission.VIEW_OWN_LEAVE_BALANCE])
async def get_leave_balances_endpoint(
    user_id: int,
    leave_type: Optional[str] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[LeaveBalanceOut]:
    """Retrieve leave balances for a user.

    Args:
        user_id: The ID of the user to retrieve balances for.
        leave_type: Optional leave type to filter balances.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        List[LeaveBalanceOut]: List of leave balances.
    """
    return await get_leave_balances_by_user_and_type(user_id, leave_type, current_user, db)

@router.put(
    "/{user_id}/{leave_type}/{balance_change}",
    response_model=LeaveBalanceOut,
    summary="Update leave balance",
    description="Update or accrue/deduct leave balance for a user."
)
@require_permissions([Permission.UPDATE_LEAVE_BALANCE])
async def update_leave_balance_endpoint(
    user_id: int,
    leave_type: str,
    balance_change: float,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> LeaveBalanceOut:
    """Update a leave balance.

    Args:
        user_id: The ID of the user to update the balance for.
        leave_type: The type of leave to update.
        balance_change: The amount to adjust the used_days (negative to deduct, positive to accrue).
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        LeaveBalanceOut: The updated leave balance.
    """
    return await update_leave_balance(user_id, leave_type, balance_change, request, current_user, db)