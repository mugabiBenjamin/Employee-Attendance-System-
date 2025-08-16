from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.leave_policy_service import (
    create_leave_policy,
    get_leave_policy,
    list_leave_policies,
    update_leave_policy,
    delete_leave_policy
)
from app.schemas.leave_policy import LeavePolicyCreate, LeavePolicyUpdate, LeavePolicyOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leave-policies", tags=["Leave Policies"])

@router.post("/", 
             response_model=LeavePolicyOut, 
             status_code=status.HTTP_201_CREATED,
             summary="Create a new leave policy",
             description="Create a new leave policy with role/department applicability.")
@require_permissions([Permission.MANAGE_LEAVE_POLICIES])
async def create_leave_policy_endpoint(
    leave_policy: LeavePolicyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> LeavePolicyOut:
    """
    Create a new leave policy by delegating to leave_policy_service.
    """
    return await create_leave_policy(leave_policy, current_user, db, settings)

@router.get("/{policy_id}", 
            response_model=LeavePolicyOut,
            summary="Get leave policy by ID",
            description="Retrieve a specific leave policy by its ID.")
@require_permissions([Permission.VIEW_LEAVE_POLICIES])
async def get_leave_policy_endpoint(
    policy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> LeavePolicyOut:
    """
    Retrieve a leave policy by ID by delegating to leave_policy_service.
    """
    return await get_leave_policy(policy_id, current_user, db, settings)

@router.get("/", 
            response_model=List[LeavePolicyOut],
            summary="List all leave policies",
            description="List all active leave policies with pagination.")
@require_permissions([Permission.VIEW_LEAVE_POLICIES])
async def list_leave_policies_endpoint(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[LeavePolicyOut]:
    """
    List all leave policies by delegating to leave_policy_service.
    """
    return await list_leave_policies(skip, limit, current_user, db, settings)

@router.put("/{policy_id}", 
            response_model=LeavePolicyOut,
            summary="Update a leave policy",
            description="Update an existing leave policy with role/department applicability.")
@require_permissions([Permission.MANAGE_LEAVE_POLICIES])
async def update_leave_policy_endpoint(
    policy_id: int,
    leave_policy_update: LeavePolicyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> LeavePolicyOut:
    """
    Update a leave policy by delegating to leave_policy_service.
    """
    return await update_leave_policy(policy_id, leave_policy_update, current_user, db, settings)

@router.delete("/{policy_id}", 
               status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete a leave policy",
               description="Soft delete a leave policy.")
@require_permissions([Permission.MANAGE_LEAVE_POLICIES])
async def delete_leave_policy_endpoint(
    policy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> None:
    """
    Soft delete a leave policy by delegating to leave_policy_service.
    """
    await delete_leave_policy(policy_id, current_user, db, settings)