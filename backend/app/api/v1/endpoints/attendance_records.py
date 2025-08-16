from fastapi import APIRouter, Depends, Request, HTTPException
from typing import List
from app.services.attendance_record_service import clock_in, clock_out, get_attendance_history
from app.models.users import Users
from app.core.security import get_current_user
from app.core.database import get_db
from app.core.permissions import require_employee_permissions, require_permissions
from app.core.enums import Permission
from app.core.config import Settings, get_settings
from app.schemas.attendance_record import AttendanceRecordOut, ClockInOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attendance-records", tags=["Attendance Records"])

@router.post("/clock", 
            response_model=AttendanceRecordOut, 
            status_code=201,
            summary="Clock in or out", 
            description="Record clock-in or clock-out for an employee.")
@require_employee_permissions()
async def clock_in_out_endpoint(
    request: Request,
    clock_data: ClockInOut,
    db=Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> AttendanceRecordOut:
    """
    Handle clock-in or clock-out by delegating to service layer.
    """
    if clock_data.action == "clock_in":
        return await clock_in(request, current_user, None, db)
    elif clock_data.action == "clock_out":
        return await clock_out(request, current_user, db)
    else:
        logger.error(f"Invalid clock action: {clock_data.action}")
        raise HTTPException(status_code=400, detail="Invalid action. Must be 'clock_in' or 'clock_out'")

@router.get("/history", 
            response_model=List[AttendanceRecordOut],
            summary="Get attendance history", 
            description="Retrieve attendance history for the current user with pagination.")
@require_permissions([Permission.VIEW_OWN_ATTENDANCE])
async def get_attendance_history_endpoint(
    skip: int = 0,
    limit: int = 50,
    db=Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> List[AttendanceRecordOut]:
    """
    Retrieve attendance history by delegating to service layer.
    """
    return await get_attendance_history(current_user, None, None, skip, limit, db, settings)