from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import date
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.overtime_record_service import (
    create_overtime_record,
    get_overtime_record,
    get_user_overtime_records,
    get_team_overtime_records,
    approve_overtime_record
)
from app.schemas.overtime_record import OvertimeRecordCreate, OvertimeRecordOut, OvertimeRecordApproval
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
    db: AsyncSession = Depends(get_db)
) -> OvertimeRecordOut:
    """Create a new overtime record.

    Args:
        overtime: Overtime record creation data.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        OvertimeRecordOut: The created overtime record.
    """
    return await create_overtime_record(overtime, request, current_user, db)

@router.get(
    "/{overtime_id}",
    response_model=OvertimeRecordOut,
    summary="Get overtime record by ID",
    description="Retrieve an overtime record by its ID."
)
@require_permissions([Permission.VIEW_OVERTIME_RECORD, Permission.VIEW_OWN_OVERTIME_RECORD])
async def get_overtime_record_endpoint(
    overtime_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> OvertimeRecordOut:
    """Retrieve an overtime record by ID.

    Args:
        overtime_id: The ID of the overtime record to retrieve.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        OvertimeRecordOut: The retrieved overtime record.
    """
    return await get_overtime_record(overtime_id, current_user, db)

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
    limit: int = 50,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[OvertimeRecordOut]:
    """List overtime records for a specific user.

    Args:
        user_id: The ID of the user to retrieve records for.
        start_date: Optional start date filter.
        end_date: Optional end date filter.
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return.
        current_user: The authenticated user.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[OvertimeRecordOut]: List of overtime records.
    """
    return await get_user_overtime_records(user_id, start_date, end_date, skip, limit, current_user, db, settings)

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
    limit: int = 50,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[OvertimeRecordOut]:
    """List overtime records for a manager's team.

    Args:
        start_date: Optional start date filter.
        end_date: Optional end date filter.
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return.
        current_user: The authenticated user (manager).
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[OvertimeRecordOut]: List of team overtime records.
    """
    return await get_team_overtime_records(start_date, end_date, skip, limit, current_user, db, settings)

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
    db: AsyncSession = Depends(get_db)
) -> OvertimeRecordOut:
    """Approve or reject an overtime record.

    Args:
        record_id: The ID of the overtime record to approve/reject.
        approval: Approval data containing status and comments.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        OvertimeRecordOut: The updated overtime record.
    """
    return await approve_overtime_record(record_id, approval, request, current_user, db)