from fastapi import APIRouter, Depends, HTTPException, status, Request
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
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system-logs", tags=["System Logs"])

@router.post(
    "/",
    response_model=SystemLogOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create system log",
    description="Create a new system log entry."
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
    try:
        request_id = get_request_id(request)
        return await service_create_system_log(log, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error creating system log: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating system log: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/{log_id}",
    response_model=SystemLogOut,
    summary="Get system log by ID",
    description="Retrieve a specific system log by its ID."
)
async def read_system_log_endpoint(
    log_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.VIEW_LOGS]))
) -> SystemLogOut:
    """Retrieve a system log by ID."""
    try:
        request_id = get_request_id(request)
        return await service_read_system_log(log_id, db, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving system log {log_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving system log {log_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/",
    response_model=List[SystemLogOut],
    summary="List system logs",
    description="List system logs with optional filters for user, action, table affected, department, date range, and active status."
)
async def read_system_logs_endpoint(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    table_affected: Optional[str] = None,
    department_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    request: Request = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_LOGS]))
) -> List[SystemLogOut]:
    """List system logs with optional filters and pagination."""
    try:
        request_id = get_request_id(request)
        return await service_read_system_logs(user_id, action, table_affected, department_id, start_date, end_date, is_active, skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error listing system logs: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing system logs: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/user/{user_id}/logs",
    response_model=List[SystemLogOut],
    summary="Get logs for specific user",
    description="Retrieve system logs for a specific user, optionally filtered by action and table affected."
)
async def get_user_logs_endpoint(
    user_id: int,
    action: Optional[str] = None,
    table_affected: Optional[str] = None,
    limit: Optional[int] = None,
    request: Request = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_LOGS]))
) -> List[SystemLogOut]:
    """Retrieve logs for a specific user."""
    try:
        request_id = get_request_id(request)
        return await service_get_user_logs(user_id, action, table_affected, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving logs for user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving logs for user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/actions/summary",
    response_model=List[SystemLogActionSummary],
    summary="Get log action summary",
    description="Retrieve a summary of system actions with occurrence counts, optionally filtered by user, department, and date range."
)
async def get_log_actions_summary_endpoint(
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.VIEW_LOGS]))
) -> List[SystemLogActionSummary]:
    """Retrieve a summary of system actions with occurrence counts."""
    try:
        request_id = get_request_id(request)
        return await service_get_log_actions_summary(user_id, department_id, start_date, end_date, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving log actions summary: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving log actions summary: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{log_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete system log",
    description="Soft delete a system log by its ID."
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
    try:
        request_id = get_request_id(request)
        await service_delete_system_log(log_id, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error deleting system log {log_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting system log {log_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")