from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission, LeaveType
from app.core.exceptions import ValidationError
from app.services.leave_balance_service import (
    get_leave_balances_by_user_and_type,
    update_leave_balance
)
from app.schemas.leave_balance import LeaveBalanceOut
import logging

logger = logging.getLogger(__name__)

def get_request_id(request: Request) -> Optional[str]:
    """Extract request_id from the request state."""
    return request.state.request_id if hasattr(request.state, "request_id") else None

router = APIRouter(prefix="/leave-balances", tags=["Leave Balances"])

@router.get(
    "/{user_id}",
    response_model=List[LeaveBalanceOut],
    summary="Get leave balances by user and type",
    description="Retrieve leave balances for a specific user, optionally filtered by leave type."
)
@require_permissions([Permission.VIEW_LEAVE_BALANCE, Permission.VIEW_OWN_LEAVE_BALANCE])
async def get_leave_balances_endpoint(
    request: Request,
    user_id: int,
    leave_type: Optional[LeaveType] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[LeaveBalanceOut]:
    """Retrieve leave balances for a user."""
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user_id")
        request_id = get_request_id(request)
        return await get_leave_balances_by_user_and_type(user_id, leave_type, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error retrieving leave balances for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave balances for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{user_id}/{leave_type}/{balance_change}/{version}",
    response_model=LeaveBalanceOut,
    summary="Update leave balance",
    description="Update or accrue/deduct leave balance for a user."
)
@require_permissions([Permission.UPDATE_LEAVE_BALANCE])
async def update_leave_balance_endpoint(
    user_id: int,
    leave_type: LeaveType,
    balance_change: float,
    version: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> LeaveBalanceOut:
    """Update a leave balance."""
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user_id")
        if version <= 0:
            raise ValidationError(detail="Invalid version")
        if abs(balance_change) > 365:
            raise ValidationError(detail="Balance change must be reasonable (within 365 days)")
        request_id = get_request_id(request)
        return await update_leave_balance(user_id, leave_type, balance_change, version, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error updating leave balance for user_id {user_id}, leave_type {leave_type}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating leave balance for user_id {user_id}, leave_type {leave_type}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")