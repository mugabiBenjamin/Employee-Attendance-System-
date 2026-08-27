from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import LeaveType, Permission
from app.core.utils import get_request_id
from app.services.leave_balance_service import (
    get_leave_balances_by_user_and_type,
    update_leave_balance
)
from app.schemas.leave_balance import LeaveBalanceOut
from app.core.permissions import require_any_permissions_dependency, require_permissions_dependency

router = APIRouter(prefix="/leave-balances", tags=["Leave Balances"])

@router.get(
    "/{user_id}",
    response_model=List[LeaveBalanceOut],
    summary="Get leave balances by user and type"
)
async def get_leave_balances_endpoint(
    request: Request,
    user_id: int,
    leave_type: Optional[LeaveType] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_any_permissions_dependency([Permission.VIEW_LEAVE_BALANCE, Permission.VIEW_OWN_LEAVE_BALANCE]))
) -> List[LeaveBalanceOut]:
    """Retrieve leave balances for a user."""
    request_id = get_request_id(request)
    return await get_leave_balances_by_user_and_type(user_id, leave_type, current_user, db, settings, request_id)

@router.put(
    "/{user_id}/{leave_type}/{balance_change}/{version}",
    response_model=LeaveBalanceOut,
    summary="Update leave balance"
)
async def update_leave_balance_endpoint(
    user_id: int,
    leave_type: LeaveType,
    balance_change: float,
    version: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.UPDATE_LEAVE_BALANCE]))
) -> LeaveBalanceOut:
    """Update a leave balance."""
    request_id = get_request_id(request)
    return await update_leave_balance(user_id, leave_type, balance_change, version, request, current_user, db, settings, request_id)