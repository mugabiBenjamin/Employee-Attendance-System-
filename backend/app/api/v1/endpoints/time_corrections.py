from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.enums import Permission, CorrectionStatus
from app.core.config import Settings, get_settings
from app.services.time_correction_service import (
    create_time_correction as service_create_time_correction,
    get_time_correction as service_get_time_correction,
    get_user_time_corrections as service_get_user_time_corrections,
    update_time_correction as service_update_time_correction,
    delete_time_correction as service_delete_time_correction
)
from app.schemas.time_correction import TimeCorrectionCreate, TimeCorrectionUpdate, TimeCorrectionOut, TimeCorrectionApproval
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
@require_permissions([Permission.CREATE_TIME_CORRECTION])
async def request_time_correction(
    correction: TimeCorrectionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> TimeCorrectionOut:
    """
    Submit a time correction request for an attendance record.

    Args:
        correction: The time correction data to create.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        current_user: The authenticated user performing the action.
        settings: Application settings.

    Returns:
        TimeCorrectionOut: The created time correction request.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        # Override user_id to ensure requests are for self only
        correction.user_id = current_user.user_id
        # Set status to UNDER_REVIEW
        correction.status = CorrectionStatus.UNDER_REVIEW
        return await service_create_time_correction(correction, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error requesting time correction for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error requesting time correction for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/{correction_id}",
    response_model=TimeCorrectionOut,
    summary="Get time correction by ID",
    description="Retrieve a specific time correction request."
)
@require_permissions([Permission.VIEW_TIME_CORRECTION])
async def get_time_correction(
    correction_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> TimeCorrectionOut:
    """
    Retrieve a specific time correction request.

    Args:
        correction_id: The ID of the time correction to retrieve.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        current_user: The authenticated user performing the action.

    Returns:
        TimeCorrectionOut: The retrieved time correction.

    Raises:
        HTTPException: For not found (404), forbidden (403), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        correction = await service_get_time_correction(correction_id, db, request_id)
        # Check if user is authorized (owns correction or has permission)
        if correction.user_id != current_user.user_id:
            await require_permissions([Permission.VIEW_TIME_CORRECTION])(current_user, db)
        return correction
    except HTTPException as e:
        logger.error(f"Error retrieving time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/",
    response_model=List[TimeCorrectionOut],
    summary="List time correction requests",
    description="Retrieve time correction requests for current user or specified user (if authorized)."
)
@require_permissions([Permission.VIEW_TIME_CORRECTION])
async def list_time_corrections(
    request: Request,
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> List[TimeCorrectionOut]:
    """
    Retrieve time correction requests for current user or specified user (if authorized).

    Args:
        user_id: Optional ID of the user to retrieve corrections for (default: current user).
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: 100).
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        current_user: The authenticated user performing the action.
        settings: Application settings.

    Returns:
        List[TimeCorrectionOut]: List of time correction requests.

    Raises:
        HTTPException: For not found (404), forbidden (403), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        target_user_id = user_id if user_id else current_user.user_id
        if target_user_id != current_user.user_id:
            await require_permissions([Permission.VIEW_TIME_CORRECTION])(current_user, db)
        return await service_get_user_time_corrections(target_user_id, skip, limit, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving time corrections for user_id {user_id or current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving time corrections for user_id {user_id or current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{correction_id}/approve",
    response_model=TimeCorrectionOut,
    summary="Approve or reject a time correction",
    description="Approve or reject a time correction request."
)
@require_permissions([Permission.UPDATE_TIME_CORRECTION])
async def approve_reject_time_correction(
    correction_id: int,
    approval_data: TimeCorrectionApproval,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> TimeCorrectionOut:
    """
    Approve or reject a time correction request.

    Args:
        correction_id: The ID of the time correction to approve/reject.
        approval_data: The approval status data (APPROVED or REJECTED).
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        current_user: The authenticated user performing the action.
        settings: Application settings.

    Returns:
        TimeCorrectionOut: The updated time correction.

    Raises:
        HTTPException: For validation errors (422), not found (404), forbidden (403), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        if approval_data.status not in [CorrectionStatus.APPROVED, CorrectionStatus.REJECTED]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Status must be 'APPROVED' or 'REJECTED'"
            )
        update_data = TimeCorrectionUpdate(status=approval_data.status)
        correction = await service_update_time_correction(correction_id, update_data, request, current_user, db, settings, request_id)
        logger.info(
            f"Time correction {correction_id} {approval_data.status.value} by user_id: {current_user.user_id}",
            extra={"request_id": request_id}
        )
        return correction
    except HTTPException as e:
        logger.error(f"Error processing time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{correction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a time correction",
    description="Soft delete a time correction request (HR/admin only)."
)
@require_permissions([Permission.DELETE_TIME_CORRECTION])
async def remove_time_correction(
    correction_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> None:
    """
    Soft delete a time correction request (HR/admin only).

    Args:
        correction_id: The ID of the time correction to delete.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        current_user: The authenticated user performing the action.
        settings: Application settings.

    Returns:
        None: No content returned on successful deletion.

    Raises:
        HTTPException: For not found (404), forbidden (403), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        await service_delete_time_correction(correction_id, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error deleting time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting time correction {correction_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")