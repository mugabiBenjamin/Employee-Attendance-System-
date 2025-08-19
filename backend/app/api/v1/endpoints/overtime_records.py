from fastapi import APIRouter, Depends, status, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import date
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.core.exceptions import ValidationError
from app.services.overtime_record_service import (
    create_overtime_record,
    get_overtime_record,
    get_user_overtime_records,
    get_team_overtime_records,
    update_overtime_record,
    approve_overtime_record,
    delete_overtime_record
)
from app.schemas.overtime_record import OvertimeRecordCreate, OvertimeRecordUpdate, OvertimeRecordOut, OvertimeRecordApproval
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/overtime-records", tags=["Overtime Records"])

@router.post(
    "/",
    response_model=OvertimeRecordOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an overtime record",
    description="Create a new overtime record with validation and notification."
)
@require_permissions([Permission.CREATE_OVERTIME_RECORD])
async def create_overtime_record_endpoint(
    overtime: OvertimeRecordCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> OvertimeRecordOut:
    """Create a new overtime record."""
    try:
        request_id = getattr(request.state, "request_id", None)
        return await create_overtime_record(overtime, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error creating overtime record: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating overtime record: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/{overtime_id}",
    response_model=OvertimeRecordOut,
    summary="Get overtime record by ID",
    description="Retrieve an overtime record by its ID."
)
@require_permissions([Permission.VIEW_OVERTIME_RECORD, Permission.VIEW_OWN_OVERTIME_RECORD])
async def get_overtime_record_endpoint(
    overtime_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> OvertimeRecordOut:
    """Retrieve an overtime record by ID."""
    try:
        if overtime_id <= 0:
            raise ValidationError(detail="Invalid overtime ID")
        request_id = getattr(request.state, "request_id", None)
        return await get_overtime_record(overtime_id, current_user, db, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error retrieving overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/user/{user_id}",
    response_model=List[OvertimeRecordOut],
    summary="List user overtime records",
    description="List overtime records for a specific user with optional date range and pagination."
)
@require_permissions([Permission.VIEW_OVERTIME_RECORD, Permission.VIEW_OWN_OVERTIME_RECORD])
async def get_user_overtime_records_endpoint(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    request: Request = Depends(),
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[OvertimeRecordOut]:
    """List overtime records for a specific user."""
    try:
        request_id = getattr(request.state, "request_id", None)
        return await get_user_overtime_records(user_id, start_date, end_date, skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error listing user overtime records: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing user overtime records: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/team",
    response_model=List[OvertimeRecordOut],
    summary="List team overtime records",
    description="List overtime records for a manager's team with optional date range and pagination."
)
@require_permissions([Permission.VIEW_TEAM_OVERTIME_RECORDS])
async def get_team_overtime_records_endpoint(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    request: Request = Depends(),
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[OvertimeRecordOut]:
    """List overtime records for a manager's team."""
    try:
        request_id = getattr(request.state, "request_id", None)
        return await get_team_overtime_records(start_date, end_date, skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error listing team overtime records: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing team overtime records: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{overtime_id}",
    response_model=OvertimeRecordOut,
    summary="Update an overtime record",
    description="Update an existing overtime record."
)
@require_permissions([Permission.UPDATE_OVERTIME])
async def update_overtime_record_endpoint(
    overtime_id: int,
    overtime_update: OvertimeRecordUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> OvertimeRecordOut:
    """Update an overtime record."""
    try:
        if overtime_id <= 0:
            raise ValidationError(detail="Invalid overtime ID")
        request_id = getattr(request.state, "request_id", None)
        return await update_overtime_record(overtime_id, overtime_update, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error updating overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{record_id}/approve",
    response_model=OvertimeRecordOut,
    summary="Approve or reject an overtime record",
    description="Approve or reject an overtime record with status update and notification."
)
@require_permissions([Permission.APPROVE_OVERTIME])
async def approve_overtime_record_endpoint(
    record_id: int,
    approval: OvertimeRecordApproval,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> OvertimeRecordOut:
    """Approve or reject an overtime record."""
    try:
        if record_id <= 0:
            raise ValidationError(detail="Invalid overtime ID")
        request_id = getattr(request.state, "request_id", None)
        return await approve_overtime_record(record_id, approval, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error approving overtime record {record_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error approving overtime record {record_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{overtime_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an overtime record",
    description="Soft delete an overtime record."
)
@require_permissions([Permission.DELETE_OVERTIME])
async def delete_overtime_record_endpoint(
    overtime_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> None:
    """Soft delete an overtime record."""
    try:
        if overtime_id <= 0:
            raise ValidationError(detail="Invalid overtime ID")
        request_id = getattr(request.state, "request_id", None)
        await delete_overtime_record(overtime_id, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error deleting overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")