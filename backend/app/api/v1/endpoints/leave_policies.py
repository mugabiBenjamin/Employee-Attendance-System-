from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
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

@router.post(
    "/",
    response_model=LeavePolicyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new leave policy",
    description="Create a new leave policy with role/department applicability."
)
@require_permissions([Permission.CREATE_LEAVE_POLICY])
async def create_leave_policy_endpoint(
    policy: LeavePolicyCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> LeavePolicyOut:
    """Create a new leave policy.

    Args:
        policy: Leave policy creation data.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        LeavePolicyOut: The created leave policy.
    """
    return await create_leave_policy(policy, request, current_user, db)

@router.get(
    "/{policy_id}",
    response_model=LeavePolicyOut,
    summary="Get leave policy by ID",
    description="Retrieve a specific leave policy by its ID."
)
@require_permissions([Permission.VIEW_LEAVE_POLICY, Permission.VIEW_OWN_LEAVE_POLICY])
async def get_leave_policy_endpoint(
    policy_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> LeavePolicyOut:
    """Retrieve a leave policy by ID.

    Args:
        policy_id: The ID of the leave policy to retrieve.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        LeavePolicyOut: The retrieved leave policy.
    """
    return await get_leave_policy(policy_id, current_user, db)

@router.get(
    "/",
    response_model=List[LeavePolicyOut],
    summary="List all leave policies",
    description="List all active leave policies with pagination."
)
@require_permissions([Permission.VIEW_LEAVE_POLICY, Permission.VIEW_OWN_LEAVE_POLICY])
async def list_leave_policies_endpoint(
    skip: int = 0,
    limit: int = 50,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[LeavePolicyOut]:
    """List all active leave policies with pagination.

    Args:
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return.
        current_user: The authenticated user.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[LeavePolicyOut]: List of active leave policies.
    """
    return await list_leave_policies(skip, limit, current_user, db, settings)

@router.put(
    "/{policy_id}",
    response_model=LeavePolicyOut,
    summary="Update a leave policy",
    description="Update an existing leave policy with role/department applicability."
)
@require_permissions([Permission.UPDATE_LEAVE_POLICY])
async def update_leave_policy_endpoint(
    policy_id: int,
    policy_update: LeavePolicyUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> LeavePolicyOut:
    """Update a leave policy.

    Args:
        policy_id: The ID of the leave policy to update.
        policy_update: Leave policy update data.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        LeavePolicyOut: The updated leave policy.
    """
    return await update_leave_policy(policy_id, policy_update, request, current_user, db)

@router.delete(
    "/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a leave policy",
    description="Soft delete a leave policy."
)
@require_permissions([Permission.DELETE_LEAVE_POLICY])
async def delete_leave_policy_endpoint(
    policy_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> None:
    """Soft delete a leave policy.

    Args:
        policy_id: The ID of the leave policy to delete.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.
    """
    await delete_leave_policy(policy_id, request, current_user, db)