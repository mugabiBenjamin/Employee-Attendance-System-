from datetime import date
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.overtime_record_service import (
    create_overtime_record,
    approve_overtime_record,
    list_overtime_records
)
from app.schemas.overtime_record import OvertimeRecordCreate, OvertimeRecordApproval, OvertimeRecordOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/overtime-records", tags=["Overtime Records"])

@router.post("/", 
             response_model=OvertimeRecordOut, 
             status_code=status.HTTP_201_CREATED,
             summary="Create an overtime record",
             description="Create a new overtime record with calculated hours.")
@require_permissions([Permission.REQUEST_OVERTIME])
async def create_overtime_record_endpoint(
    overtime_record: OvertimeRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> OvertimeRecordOut:
    """
    Create an overtime record by delegating to overtime_record_service.
    """
    return await create_overtime_record(overtime_record, current_user, db, settings)

@router.put("/{record_id}/approve", 
            response_model=OvertimeRecordOut,
            summary="Approve or reject an overtime record",
            description="Approve or reject an overtime record with status update.")
@require_permissions([Permission.APPROVE_OVERTIME])
async def approve_overtime_record_endpoint(
    record_id: int,
    approval_data: OvertimeRecordApproval,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> OvertimeRecordOut:
    """
    Approve or reject an overtime record by delegating to overtime_record_service.
    """
    return await approve_overtime_record(record_id, approval_data, current_user, db, settings)

@router.get("/", 
            response_model=List[OvertimeRecordOut],
            summary="List overtime records",
            description="List overtime records with optional user and date filters.")
@require_permissions([Permission.VIEW_TEAM_ATTENDANCE])
async def list_overtime_records_endpoint(
    user_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> List[OvertimeRecordOut]:
    """
    List overtime records by delegating to overtime_record_service.
    """
    return await list_overtime_records(user_id, start_date, end_date, skip, limit, current_user, db, settings)