from fastapi import APIRouter, Depends, Request
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
from app.core.permissions import require_permissions_dependency

router = APIRouter(prefix="/overtime-records", tags=["Overtime Records"])

@router.post(
    "/",
    response_model=OvertimeRecordOut,
    status_code=201,
    summary="Create an overtime record"
)
async def create_overtime_record_endpoint(
    overtime: OvertimeRecordCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.CREATE_OVERTIME_RECORD]))
) -> OvertimeRecordOut:
    """Create a new overtime record."""
    request_id = get_request_id(request)
    return await create_overtime_record(overtime, request, current_user, db, settings, request_id)

@router.get(
    "/{overtime_id}",
    response_model=OvertimeRecordOut,
    summary="Get overtime record by ID"
)
async def get_overtime_record_endpoint(
    overtime_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.VIEW_OVERTIME_RECORD, Permission.VIEW_OWN_OVERTIME_RECORD]))
) -> OvertimeRecordOut:
    """Retrieve an overtime record by ID."""
    request_id = get_request_id(request)
    return await get_overtime_record(overtime_id, current_user, db, request_id)

@router.get(
    "/user/{user_id}",
    response_model=List[OvertimeRecordOut],
    summary="List user overtime records"
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
    _=Depends(require_permissions_dependency([Permission.VIEW_OVERTIME_RECORD, Permission.VIEW_OWN_OVERTIME_RECORD]))
) -> List[OvertimeRecordOut]:
    """List overtime records for a specific user."""
    request_id = get_request_id(request)
    return await get_user_overtime_records(user_id, status, start_date, end_date, skip, limit, current_user, db, settings, request_id)

@router.get(
    "/team",
    response_model=List[OvertimeRecordOut],
    summary="List team overtime records"
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
    _=Depends(require_permissions_dependency([Permission.VIEW_TEAM_OVERTIME_RECORDS]))
) -> List[OvertimeRecordOut]:
    """List overtime records for a manager's team."""
    request_id = get_request_id(request)
    return await get_team_overtime_records(status, start_date, end_date, skip, limit, current_user, db, settings, request_id)

@router.put(
    "/{overtime_id}",
    response_model=OvertimeRecordOut,
    summary="Update an overtime record"
)
async def update_overtime_record_endpoint(
    overtime_id: int,
    overtime_update: OvertimeRecordUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.UPDATE_OVERTIME]))
) -> OvertimeRecordOut:
    """Update an overtime record."""
    request_id = get_request_id(request)
    return await update_overtime_record(overtime_id, overtime_update, request, current_user, db, settings, request_id)

@router.put(
    "/{record_id}/approve",
    response_model=OvertimeRecordOut,
    summary="Approve or reject an overtime record"
)
async def approve_overtime_record_endpoint(
    record_id: int,
    approval: OvertimeRecordApproval,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.APPROVE_OVERTIME]))
) -> OvertimeRecordOut:
    """Approve or reject an overtime record."""
    request_id = get_request_id(request)
    return await approve_overtime_record(record_id, approval, request, current_user, db, settings, request_id)

@router.delete(
    "/{overtime_id}",
    status_code=204,
    summary="Delete an overtime record"
)
async def delete_overtime_record_endpoint(
    overtime_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.DELETE_OVERTIME]))
) -> None:
    """Soft delete an overtime record."""
    request_id = get_request_id(request)
    await delete_overtime_record(overtime_id, request, current_user, db, settings, request_id)