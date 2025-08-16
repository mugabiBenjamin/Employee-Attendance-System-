from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.leave_balance_service import (
    get_leave_balances_by_user_and_type,
    update_leave_balance
)
from app.schemas.leave_balance import LeaveBalanceUpdate, LeaveBalanceOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leave-balances", tags=["Leave Balances"])

@router.get("/{user_id}", 
            response_model=List[LeaveBalanceOut],
            summary="Get leave balances by user and type",
            description="Retrieve leave balances for a specific user, optionally filtered by leave type.")
@require_permissions([Permission.VIEW_OWN_ATTENDANCE, Permission.MANAGE_LEAVE_BALANCES])
async def get_leave_balances_endpoint(
    user_id: int,
    leave_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[LeaveBalanceOut]:
    """
    Retrieve leave balances for a user by delegating to leave_balance_service.
    """
    return await get_leave_balances_by_user_and_type(
        user_id=user_id,
        leave_type=leave_type,
        current_user=current_user,
        db=db,
        settings=settings
    )

@router.put("/{user_id}", 
            response_model=LeaveBalanceOut,
            summary="Update leave balance",
            description="Update or accrue/deduct leave balance for a user.")
@require_permissions([Permission.MANAGE_LEAVE_BALANCES])
async def update_leave_balance_endpoint(
    user_id: int,
    leave_balance_update: LeaveBalanceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> LeaveBalanceOut:
    """
    Update a leave balance by delegating to leave_balance_service.
    """
    return await update_leave_balance(
        user_id=user_id,
        leave_balance_update=leave_balance_update,
        current_user=current_user,
        db=db,
        settings=settings
    )