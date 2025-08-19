from fastapi import APIRouter, Depends, status, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.core.exceptions import ValidationError
from app.core.utils import get_request_id
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
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> LeavePolicyOut:
    """Create a new leave policy."""
    try:
        request_id = get_request_id(request)
        return await create_leave_policy(policy, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
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
@require_permissions([Permission.VIEW_LEAVE_POLICY, Permission.VIEW_OWN_LEAVE_POLICY])
async def get_leave_policy_endpoint(
    policy_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> LeavePolicyOut:
    """Retrieve a leave policy by ID."""
    try:
        if policy_id <= 0:
            raise ValidationError(detail="Invalid policy_id")
        request_id = get_request_id(request)
        return await get_leave_policy(policy_id, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
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
    description="List all active leave policies with pagination."
)
@require_permissions([Permission.VIEW_LEAVE_POLICY, Permission.VIEW_OWN_LEAVE_POLICY])
async def list_leave_policies_endpoint(
    request: Request,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[LeavePolicyOut]:
    """List all active leave policies with pagination."""
    try:
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")
        request_id = get_request_id(request)
        return await list_leave_policies(skip, limit, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
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
    description="Update an existing leave policy with role/department applicability."
)
@require_permissions([Permission.UPDATE_LEAVE_POLICY])
async def update_leave_policy_endpoint(
    policy_id: int,
    policy_update: LeavePolicyUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> LeavePolicyOut:
    """Update a leave policy."""
    try:
        if policy_id <= 0:
            raise ValidationError(detail="Invalid policy_id")
        request_id = get_request_id(request)
        return await update_leave_policy(policy_id, policy_update, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
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
@require_permissions([Permission.DELETE_LEAVE_POLICY])
async def delete_leave_policy_endpoint(
    policy_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> None:
    """Soft delete a leave policy."""
    try:
        if policy_id <= 0:
            raise ValidationError(detail="Invalid policy_id")
        request_id = get_request_id(request)
        await delete_leave_policy(policy_id, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error deleting leave policy {policy_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting leave policy {policy_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")