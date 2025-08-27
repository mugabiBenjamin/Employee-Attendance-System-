from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.enums import CorrectionStatus, Permission
from app.core.config import Settings, get_settings
from app.core.utils import get_request_id
from app.services.time_correction_service import (
    create_time_correction as service_create_time_correction,
    get_time_correction as service_get_time_correction,
    get_user_time_corrections as service_get_user_time_corrections,
    get_department_time_corrections as service_get_department_time_corrections,
    update_time_correction as service_update_time_correction,
    approve_time_correction as service_approve_time_correction,
    delete_time_correction as service_delete_time_correction
)
from app.schemas.time_correction import TimeCorrectionCreate, TimeCorrectionUpdate, TimeCorrectionOut, TimeCorrectionApproval
from app.core.exceptions import ValidationError
from app.core.permissions import require_permissions, require_any_permissions
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/time-corrections", tags=["Time Corrections"])

@router.post(
    "/",
    response_model=TimeCorrectionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Request a time correction",
    description="Submit a time correction request for an attendance record."
)
async def request_time_correction(
    correction: TimeCorrectionCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.CREATE_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """Submit a time correction request for an attendance record."""
    try:
        request_id = get_request_id(request)
        return await service_create_time_correction(correction, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error requesting time correction for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error requesting time correction for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/{correction_id}",
    response_model=TimeCorrectionOut,
    summary="Get time correction by ID",
    description="Retrieve a specific time correction request."
)
async def get_time_correction(
    correction_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_any_permissions([Permission.VIEW_TIME_CORRECTION, Permission.MANAGE_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """Retrieve a specific time correction request."""
    try:
        request_id = get_request_id(request)
        return await service_get_time_correction(correction_id, current_user, db, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving time correction {correction_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving time correction {correction_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/",
    response_model=List[TimeCorrectionOut],
    summary="List time correction requests",
    description="Retrieve time correction requests for current user, specified user, or department (if authorized)."
)
async def list_time_corrections(
    request: Request,
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    status: Optional[CorrectionStatus] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_any_permissions([Permission.VIEW_TIME_CORRECTION, Permission.MANAGE_TIME_CORRECTION]))
) -> List[TimeCorrectionOut]:
    """Retrieve time correction requests for current user, specified user, or department."""
    try:
        request_id = get_request_id(request)
        if user_id and department_id:
            raise ValidationError(detail="Cannot specify both user_id and department_id")
        
        if department_id:
            return await service_get_department_time_corrections(department_id, skip, limit, status, current_user, db, settings, request_id)
        
        target_user_id = user_id if user_id else current_user.user_id
        return await service_get_user_time_corrections(target_user_id, skip, limit, status, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error retrieving time corrections for user_id {user_id or current_user.user_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving time corrections for user_id {user_id or current_user.user_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{correction_id}",
    response_model=TimeCorrectionOut,
    summary="Update a time correction",
    description="Update an existing time correction request."
)
async def update_time_correction(
    correction_id: int,
    time_correction_update: TimeCorrectionUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.UPDATE_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """Update an existing time correction request."""
    try:
        request_id = get_request_id(request)
        return await service_update_time_correction(correction_id, time_correction_update, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error updating time correction {correction_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating time correction {correction_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{correction_id}/approve",
    response_model=TimeCorrectionOut,
    summary="Approve or reject a time correction",
    description="Approve or reject a time correction request."
)
async def approve_reject_time_correction(
    correction_id: int,
    approval_data: TimeCorrectionApproval,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.MANAGE_TIME_CORRECTION]))
) -> TimeCorrectionOut:
    """Approve or reject a time correction request."""
    try:
        request_id = get_request_id(request)
        return await service_approve_time_correction(correction_id, approval_data, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error processing time correction {correction_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing time correction {correction_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{correction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a time correction",
    description="Soft delete a time correction request (HR/admin only)."
)
async def remove_time_correction(
    correction_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.DELETE_TIME_CORRECTION]))
) -> None:
    """Soft delete a time correction request (HR/admin only)."""
    try:
        request_id = get_request_id(request)
        await service_delete_time_correction(correction_id, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error deleting time correction {correction_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting time correction {correction_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")