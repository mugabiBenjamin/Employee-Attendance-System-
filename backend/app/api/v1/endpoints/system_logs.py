from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
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
    settings: Settings = Depends(get_settings)
) -> SystemLogOut:
    """Create a new system log entry.

    Args:
        log: The system log data to create.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action (optional).
        db: Database session dependency.
        settings: Application settings.

    Returns:
        SystemLogOut: The created system log record.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
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
@require_permissions([Permission.VIEW_LOGS])
async def read_system_log_endpoint(
    log_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> SystemLogOut:
    """Retrieve a system log by ID.

    Args:
        log_id: The ID of the system log to retrieve.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.

    Returns:
        SystemLogOut: The requested system log record.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
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
@require_permissions([Permission.VIEW_LOGS])
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
    request: Request = Depends(),
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[SystemLogOut]:
    """List system logs with optional filters and pagination.

    Args:
        user_id: Optional user ID to filter logs.
        action: Optional action to filter logs.
        table_affected: Optional table name to filter logs.
        department_id: Optional department ID to filter logs.
        start_date: Optional start date to filter logs.
        end_date: Optional end date to filter logs.
        is_active: Optional filter for active/inactive logs.
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[SystemLogOut]: List of system log records.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), or server errors (500).
    """
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
@require_permissions([Permission.VIEW_LOGS])
async def get_user_logs_endpoint(
    user_id: int,
    action: Optional[str] = None,
    table_affected: Optional[str] = None,
    limit: Optional[int] = None,
    request: Request = Depends(),
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[SystemLogOut]:
    """Retrieve logs for a specific user.

    Args:
        user_id: The ID of the user to retrieve logs for.
        action: Optional action to filter logs.
        table_affected: Optional table name to filter logs.
        limit: Maximum number of records to return.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[SystemLogOut]: List of system log records for the user.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), or server errors (500).
    """
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
@require_permissions([Permission.VIEW_LOGS])
async def get_log_actions_summary_endpoint(
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    request: Request = Depends(),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[SystemLogActionSummary]:
    """Retrieve a summary of system actions with occurrence counts.

    Args:
        user_id: Optional user ID to filter logs.
        department_id: Optional department ID to filter logs.
        start_date: Optional start date to filter logs.
        end_date: Optional end date to filter logs.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[SystemLogActionSummary]: Summary of actions with counts.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
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
@require_permissions([Permission.DELETE_LOGS])
async def delete_system_log_endpoint(
    log_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> None:
    """Soft delete a system log.

    Args:
        log_id: The ID of the system log to delete.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = get_request_id(request)
        await service_delete_system_log(log_id, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error deleting system log {log_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting system log {log_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")