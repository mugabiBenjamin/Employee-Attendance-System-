from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel
from app.core.database import get_db
from app.models.time_corrections import TimeCorrections
from app.core.permissions import check_permissions, require_permissions
from app.core.security import get_current_user
from app.core.enums import Permission, CorrectionStatus
from app.models.users import Users
from app.schemas.time_correction import TimeCorrectionApproval, TimeCorrectionCreate, TimeCorrectionOut, TimeCorrectionUpdate
from app.services.time_correction_service import (
    create_time_correction,
    get_time_correction_by_id,
    get_user_time_corrections,
    update_time_correction,
    delete_time_correction
)
from app.core.mail import send_time_correction_notification
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/time-corrections", tags=["Time Corrections"])

@router.post("/", 
            response_model=TimeCorrectionOut, 
            status_code=status.HTTP_201_CREATED,
            dependencies=[Depends(require_permissions([Permission.VIEW_OWN_ATTENDANCE]))],
            summary="Request time correction", 
            description="Submit a time correction request for an attendance record.")
async def request_time_correction(
    correction: TimeCorrectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> TimeCorrectionOut:
    """Submit a time correction request for an attendance record."""
    try:
        # Override user_id to ensure requests are for self only
        correction.user_id = current_user.user_id
        # Set status to UNDER_REVIEW (align with original endpoint logic)
        correction.status = CorrectionStatus.UNDER_REVIEW
        return await create_time_correction(db, correction, current_user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error requesting time correction for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error requesting time correction"
        )

@router.get("/{correction_id}", 
            response_model=TimeCorrectionOut,
            summary="Get time correction by ID", 
            description="Retrieve a specific time correction request.")
async def get_time_correction(
    correction_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> TimeCorrectionOut:
    """Retrieve a specific time correction request."""
    try:
        correction = await get_time_correction_by_id(db, correction_id)
        if correction.user_id != current_user.user_id:
            await check_permissions([Permission.VIEW_TEAM_ATTENDANCE], current_user, db)
        return correction
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving time correction {correction_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving time correction"
        )

@router.get("/", 
            response_model=List[TimeCorrectionOut],
            summary="Get time correction requests", 
            description="Retrieve time correction requests for current user or team (if authorized).")
async def list_time_corrections(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> List[TimeCorrectionOut]:
    """Retrieve time correction requests for current user or team (if authorized)."""
    try:
        target_user_id = user_id if user_id else current_user.user_id
        if target_user_id != current_user.user_id:
            await check_permissions([Permission.VIEW_TEAM_ATTENDANCE], current_user, db)
        return await get_user_time_corrections(db, target_user_id, skip, limit)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving time corrections for user_id {user_id or current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving time corrections"
        )

@router.put("/{correction_id}", 
            response_model=TimeCorrectionOut,
            dependencies=[Depends(require_permissions([Permission.APPROVE_LEAVE]))],
            summary="Approve/reject time correction", 
            description="Approve or reject a time correction request.")
async def approve_reject_time_correction(
    correction_id: int,
    approval_data: TimeCorrectionApproval,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> TimeCorrectionOut:
    """Approve or reject a time correction request."""
    try:
        if approval_data.status.lower() not in ["approved", "rejected"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Invalid status. Must be 'approved' or 'rejected'"
            )
        status_enum = CorrectionStatus.APPROVED if approval_data.status.lower() == "approved" else CorrectionStatus.REJECTED
        update_data = TimeCorrectionUpdate(status=status_enum)
        correction = await update_time_correction(db, correction_id, update_data, current_user)

        # Send email notification to user
        await send_time_correction_notification(
            user_id=correction.user_id,
            correction_id=correction_id,
            status=status_enum.value,
            clock_in=correction.corrected_clock_in,
            clock_out=correction.corrected_clock_out,
            db=db
        )

        logger.info(f"Time correction {correction_id} {status_enum.value} by user_id: {current_user.user_id}")
        return correction

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing time correction {correction_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing time correction"
        )

@router.delete("/{correction_id}", 
            status_code=status.HTTP_204_NO_CONTENT,
            dependencies=[Depends(require_permissions([Permission.APPROVE_LEAVE]))],
            summary="Delete time correction", 
            description="Soft delete a time correction request (HR/admin only).")
async def remove_time_correction(
    correction_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> None:
    """Soft delete a time correction request (HR/admin only)."""
    try:
        await delete_time_correction(db, correction_id, current_user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting time correction {correction_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting time correction"
        )