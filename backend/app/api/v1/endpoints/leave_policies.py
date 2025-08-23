from fastapi import APIRouter, Depends, status, Request, HTTPException
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
from app.core.permissions import require_permissions
from app.core.utils import get_request_id
from app.core.enums import Permission
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leave-policies", tags=["Leave Policies"])

@router.post(
    "/",
    response_model=LeavePolicyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new leave policy",
    description="Create a new leave policy with employee type and leave type applicability."
)
async def create_leave_policy_endpoint(
    policy: LeavePolicyCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.CREATE_LEAVE_POLICY]))
) -> LeavePolicyOut:
    """Create a new leave policy.

    Args:
        policy: The leave policy data to create.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        LeavePolicyOut: The created leave policy.

    Raises:
        HTTPException: For validation errors (422) or server errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await create_leave_policy(policy, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error creating leave policy: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating leave policy: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/{policy_id}",
    response_model=LeavePolicyOut,
    summary="Get leave policy by ID",
    description="Retrieve a specific leave policy by its ID."
)
async def get_leave_policy_endpoint(
    policy_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_LEAVE_POLICY, Permission.VIEW_OWN_LEAVE_POLICY]))
) -> LeavePolicyOut:
    """Retrieve a leave policy by ID.

    Args:
        policy_id: The ID of the leave policy to retrieve.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        LeavePolicyOut: The retrieved leave policy.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), or server errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await get_leave_policy(policy_id, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving leave policy {policy_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave policy {policy_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/",
    response_model=List[LeavePolicyOut],
    summary="List all leave policies",
    description="List all active leave policies with optional filtering by employee type and leave type, and pagination."
)
async def list_leave_policies_endpoint(
    employee_type: Optional[EmployeeType] = None,
    leave_type: Optional[str] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    request: Request = Depends(),
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_LEAVE_POLICY, Permission.VIEW_OWN_LEAVE_POLICY]))
) -> List[LeavePolicyOut]:
    """List all active leave policies with optional filters and pagination.

    Args:
        employee_type: Optional employee type to filter policies.
        leave_type: Optional leave type to filter policies.
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: DEFAULT_PAGE_SIZE).
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[LeavePolicyOut]: List of leave policies.

    Raises:
        HTTPException: For validation errors (422) or server errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await list_leave_policies(employee_type, leave_type, skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving leave policies: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave policies: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{policy_id}",
    response_model=LeavePolicyOut,
    summary="Update a leave policy",
    description="Update an existing leave policy with employee type and leave type applicability."
)
async def update_leave_policy_endpoint(
    policy_id: int,
    policy_update: LeavePolicyUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.UPDATE_LEAVE_POLICY]))
) -> LeavePolicyOut:
    """Update a leave policy.

    Args:
        policy_id: The ID of the leave policy to update.
        policy_update: The updated leave policy data.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        LeavePolicyOut: The updated leave policy.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await update_leave_policy(policy_id, policy_update, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error updating leave policy {policy_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating leave policy {policy_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a leave policy",
    description="Soft delete a leave policy."
)
async def delete_leave_policy_endpoint(
    policy_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.DELETE_LEAVE_POLICY]))
) -> None:
    """Soft delete a leave policy.

    Args:
        policy_id: The ID of the leave policy to delete.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        None: No content returned on successful deletion.

    Raises:
        HTTPException: For validation errors (422), not found (404), business logic errors (422), or server errors (500).
    """
    try:
        request_id = get_request_id(request)
        await delete_leave_policy(policy_id, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error deleting leave policy {policy_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting leave policy {policy_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")