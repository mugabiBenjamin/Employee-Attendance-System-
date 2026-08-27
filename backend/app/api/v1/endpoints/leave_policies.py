from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import EmployeeType
from app.services.leave_policy_service import (
    create_leave_policy,
    get_leave_policy,
    list_leave_policies,
    update_leave_policy,
    delete_leave_policy
)
from app.schemas.leave_policy import LeavePolicyCreate, LeavePolicyUpdate, LeavePolicyOut
from app.core.permissions import require_permissions_dependency
from app.core.utils import get_request_id
from app.core.enums import Permission

router = APIRouter(prefix="/leave-policies", tags=["Leave Policies"])

@router.post(
    "/",
    response_model=LeavePolicyOut,
    status_code=201,
    summary="Create a new leave policy"
)
async def create_leave_policy_endpoint(
    policy: LeavePolicyCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.CREATE_LEAVE_POLICY]))
) -> LeavePolicyOut:
    """Create a new leave policy."""
    request_id = get_request_id(request)
    return await create_leave_policy(policy, request, current_user, db, settings, request_id)

@router.get(
    "/{policy_id}",
    response_model=LeavePolicyOut,
    summary="Get leave policy by ID"
)
async def get_leave_policy_endpoint(
    policy_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_LEAVE_POLICY, Permission.VIEW_OWN_LEAVE_POLICY]))
) -> LeavePolicyOut:
    """Retrieve a leave policy by ID."""
    request_id = get_request_id(request)
    return await get_leave_policy(policy_id, current_user, db, settings, request_id)

@router.get(
    "/",
    response_model=List[LeavePolicyOut],
    summary="List all leave policies"
)
async def list_leave_policies_endpoint(
    request: Request,
    employee_type: Optional[EmployeeType] = None,
    leave_type: Optional[str] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_LEAVE_POLICY, Permission.VIEW_OWN_LEAVE_POLICY]))
) -> List[LeavePolicyOut]:
    """List all active leave policies with optional filters and pagination."""
    request_id = get_request_id(request)
    return await list_leave_policies(employee_type, leave_type, skip, limit, current_user, db, settings, request_id)

@router.put(
    "/{policy_id}",
    response_model=LeavePolicyOut,
    summary="Update a leave policy"
)
async def update_leave_policy_endpoint(
    policy_id: int,
    policy_update: LeavePolicyUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.UPDATE_LEAVE_POLICY]))
) -> LeavePolicyOut:
    """Update a leave policy."""
    request_id = get_request_id(request)
    return await update_leave_policy(policy_id, policy_update, request, current_user, db, settings, request_id)

@router.delete(
    "/{policy_id}",
    status_code=204,
    summary="Delete a leave policy"
)
async def delete_leave_policy_endpoint(
    policy_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.DELETE_LEAVE_POLICY]))
) -> None:
    """Soft delete a leave policy."""
    request_id = get_request_id(request)
    await delete_leave_policy(policy_id, request, current_user, db, settings, request_id)