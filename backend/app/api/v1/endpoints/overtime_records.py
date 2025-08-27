from fastapi import APIRouter, Depends, status, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import date
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import OvertimeStatus, Permission
from app.core.utils import get_request_id
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
from app.core.permissions import require_permissions
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/overtime-records", tags=["Overtime Records"])

@router.post(
    "/",
    response_model=OvertimeRecordOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an overtime record",
    description="Create a new overtime record with validation and notifications."
)
async def create_overtime_record_endpoint(
    overtime: OvertimeRecordCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.CREATE_OVERTIME_RECORD]))
) -> OvertimeRecordOut:
    """Create a new overtime record.

    Args:
        overtime: The overtime record data to create.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        OvertimeRecordOut: The created overtime record.

    Raises:
        HTTPException: For validation errors (422), not found (404), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await create_overtime_record(overtime, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error creating overtime record: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating overtime record: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/{overtime_id}",
    response_model=OvertimeRecordOut,
    summary="Get overtime record by ID",
    description="Retrieve a specific overtime record by its ID."
)
async def get_overtime_record_endpoint(
    overtime_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.VIEW_OVERTIME_RECORD, Permission.VIEW_OWN_OVERTIME_RECORD]))
) -> OvertimeRecordOut:
    """Retrieve an overtime record by ID.

    Args:
        overtime_id: The ID of the overtime record to retrieve.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.

    Returns:
        OvertimeRecordOut: The retrieved overtime record.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await get_overtime_record(overtime_id, current_user, db, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/user/{user_id}",
    response_model=List[OvertimeRecordOut],
    summary="List user overtime records",
    description="List overtime records for a specific user with optional status, date range, and pagination."
)
async def get_user_overtime_records_endpoint(
    request: Request,
    user_id: int,
    status: Optional[OvertimeStatus] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_OVERTIME_RECORD, Permission.VIEW_OWN_OVERTIME_RECORD]))
) -> List[OvertimeRecordOut]:
    """List overtime records for a specific user.

    Args:
        user_id: The ID of the user whose overtime records are to be retrieved.
        status: Optional filter for overtime record status (e.g., PENDING, APPROVED, REJECTED).
        start_date: Optional start date for filtering records.
        end_date: Optional end date for filtering records.
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: DEFAULT_PAGE_SIZE).
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[OvertimeRecordOut]: List of overtime records.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await get_user_overtime_records(user_id, status, start_date, end_date, skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error listing user overtime records for user_id {user_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing user overtime records for user_id {user_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/team",
    response_model=List[OvertimeRecordOut],
    summary="List team overtime records",
    description="List overtime records for a manager's team with optional status, date range, and pagination."
)
async def get_team_overtime_records_endpoint(
    request: Request,
    status: Optional[OvertimeStatus] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_TEAM_OVERTIME_RECORDS]))
) -> List[OvertimeRecordOut]:
    """List overtime records for a manager's team.

    Args:
        status: Optional filter for overtime record status (e.g., PENDING, APPROVED, REJECTED).
        start_date: Optional start date for filtering records.
        end_date: Optional end date for filtering records.
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: DEFAULT_PAGE_SIZE).
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[OvertimeRecordOut]: List of overtime records for the manager's team.

    Raises:
        HTTPException: For validation errors (422), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await get_team_overtime_records(status, start_date, end_date, skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error listing team overtime records: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing team overtime records: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{overtime_id}",
    response_model=OvertimeRecordOut,
    summary="Update an overtime record",
    description="Update an existing overtime record with new details."
)
async def update_overtime_record_endpoint(
    overtime_id: int,
    overtime_update: OvertimeRecordUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.UPDATE_OVERTIME]))
) -> OvertimeRecordOut:
    """Update an overtime record.

    Args:
        overtime_id: The ID of the overtime record to update.
        overtime_update: The updated overtime record data.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        OvertimeRecordOut: The updated overtime record.

    Raises:
        HTTPException: For validation errors (422), not found (404), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await update_overtime_record(overtime_id, overtime_update, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error updating overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{record_id}/approve",
    response_model=OvertimeRecordOut,
    summary="Approve or reject an overtime record",
    description="Approve or reject an overtime record with status update and notifications."
)
async def approve_overtime_record_endpoint(
    record_id: int,
    approval: OvertimeRecordApproval,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.APPROVE_OVERTIME]))
) -> OvertimeRecordOut:
    """Approve or reject an overtime record.

    Args:
        record_id: The ID of the overtime record to approve or reject.
        approval: The approval data including status and comments.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        OvertimeRecordOut: The updated overtime record.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        return await approve_overtime_record(record_id, approval, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error approving overtime record {record_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error approving overtime record {record_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{overtime_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an overtime record",
    description="Soft delete an overtime record with notifications."
)
async def delete_overtime_record_endpoint(
    overtime_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.DELETE_OVERTIME]))
) -> None:
    """Soft delete an overtime record.

    Args:
        overtime_id: The ID of the overtime record to delete.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        None: No content returned on successful deletion.

    Raises:
        HTTPException: For validation errors (422), not found (404), business logic errors (422), database errors (500), or unexpected errors (500).
    """
    try:
        request_id = get_request_id(request)
        await delete_overtime_record(overtime_id, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error deleting overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")