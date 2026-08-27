from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.utils import get_request_id
from app.services.system_log_service import (
    create_system_log as service_create_system_log,
    read_system_log as service_read_system_log,
    read_system_logs as service_read_system_logs,
    get_user_logs as service_get_user_logs,
    get_log_actions_summary as service_get_log_actions_summary,
    delete_system_log as service_delete_system_log
)
from app.schemas.system_log import SystemLogCreate, SystemLogOut, SystemLogActionSummary
from app.core.enums import Permission
from app.core.permissions import require_permissions_dependency

router = APIRouter(prefix="/system-logs", tags=["System Logs"])

@router.post(
    "/",
    response_model=SystemLogOut,
    status_code=201,
    summary="Create system log"
)
async def create_system_log_endpoint(
    log: SystemLogCreate,
    request: Request,
    current_user: Optional[Users] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.CREATE_LOGS]))
) -> SystemLogOut:
    """Create a new system log entry."""
    request_id = get_request_id(request)
    return await service_create_system_log(log, request, current_user, db, settings, request_id)

@router.get(
    "/{log_id}",
    response_model=SystemLogOut,
    summary="Get system log by ID"
)
async def read_system_log_endpoint(
    log_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.VIEW_LOGS]))
) -> SystemLogOut:
    """Retrieve a system log by ID."""
    request_id = get_request_id(request)
    return await service_read_system_log(log_id, db, request_id)

@router.get(
    "/",
    response_model=List[SystemLogOut],
    summary="List system logs"
)
async def read_system_logs_endpoint(
    request: Request,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    table_affected: Optional[str] = None,
    department_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_LOGS]))
) -> List[SystemLogOut]:
    """List system logs with optional filters and pagination."""
    request_id = get_request_id(request)
    return await service_read_system_logs(user_id, action, table_affected, department_id, start_date, end_date, is_active, skip, limit, current_user, db, settings, request_id)

@router.get(
    "/user/{user_id}/logs",
    response_model=List[SystemLogOut],
    summary="Get logs for specific user"
)
async def get_user_logs_endpoint(
    request: Request,
    user_id: int,
    action: Optional[str] = None,
    table_affected: Optional[str] = None,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_LOGS]))
) -> List[SystemLogOut]:
    """Retrieve logs for a specific user."""
    request_id = get_request_id(request)
    return await service_get_user_logs(user_id, action, table_affected, limit, current_user, db, settings, request_id)

@router.get(
    "/actions/summary",
    response_model=List[SystemLogActionSummary],
    summary="Get log action summary"
)
async def get_log_actions_summary_endpoint(
    request: Request,
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_LOGS]))
) -> List[SystemLogActionSummary]:
    """Retrieve a summary of system actions with occurrence counts."""
    request_id = get_request_id(request)
    return await service_get_log_actions_summary(user_id, department_id, start_date, end_date, db, settings, request_id)

@router.delete(
    "/{log_id}",
    status_code=204,
    summary="Delete system log"
)
async def delete_system_log_endpoint(
    log_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.DELETE_LOGS]))
) -> None:
    """Soft delete a system log."""
    request_id = get_request_id(request)
    await service_delete_system_log(log_id, request, current_user, db, settings, request_id)