from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.system_log_service import (
    read_system_logs as service_read_system_logs,
    read_system_log as service_read_system_log,
    get_user_logs as service_get_user_logs,
    get_log_actions_summary as service_get_log_actions_summary
)
from app.schemas.system_log import SystemLogOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system-logs", tags=["System Logs"])

@router.get("/", 
            response_model=List[SystemLogOut],
            summary="List system logs",
            description="List system logs with optional filters.")
@require_permissions([Permission.VIEW_SYSTEM_LOGS])
async def read_system_logs_endpoint(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[SystemLogOut]:
    """
    List system logs with optional filters by delegating to system_log_service.
    """
    return await service_read_system_logs(user_id, action, start_date, end_date, skip, limit, current_user, db, settings)

@router.get("/{log_id}", 
            response_model=SystemLogOut,
            summary="Get system log by ID",
            description="Retrieve a specific system log by its ID.")
@require_permissions([Permission.VIEW_SYSTEM_LOGS])
async def read_system_log_endpoint(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> SystemLogOut:
    """
    Retrieve a system log by ID by delegating to system_log_service.
    """
    return await service_read_system_log(log_id, current_user, db, settings)

@router.get("/user/{user_id}/logs", 
            response_model=List[SystemLogOut],
            summary="Get logs for specific user",
            description="Retrieve system logs for a specific user, optionally filtered by action.")
@require_permissions([Permission.VIEW_SYSTEM_LOGS])
async def get_user_logs_endpoint(
    user_id: int,
    action: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[SystemLogOut]:
    """
    Retrieve logs for a specific user by delegating to system_log_service.
    """
    return await service_get_user_logs(user_id, action, limit, current_user, db, settings)

@router.get("/actions/summary", 
            summary="Get log action summary",
            description="Retrieve a summary of system actions.")
@require_permissions([Permission.VIEW_SYSTEM_LOGS])
async def get_log_actions_summary_endpoint(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
):
    """
    Retrieve a summary of system actions by delegating to system_log_service.
    """
    return await service_get_log_actions_summary(start_date, end_date, current_user, db, settings)