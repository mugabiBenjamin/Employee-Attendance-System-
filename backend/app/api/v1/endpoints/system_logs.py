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
from app.services.system_log_service import (
    create_system_log as service_create_system_log,
    read_system_log as service_read_system_log,
    read_system_logs as service_read_system_logs,
    get_user_logs as service_get_user_logs,
    get_log_actions_summary as service_get_log_actions_summary
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
@require_permissions([Permission.CREATE_LOGS])
async def create_system_log_endpoint(
    log: SystemLogCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> SystemLogOut:
    """
    Create a new system log entry.

    Args:
        log: The system log data to create.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        current_user: The authenticated user performing the action.

    Returns:
        SystemLogOut: The created system log entry.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_create_system_log(log, request, current_user, db, request_id)
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
    """
    Retrieve a system log by ID.

    Args:
        log_id: The ID of the system log to retrieve.
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.

    Returns:
        SystemLogOut: The retrieved system log.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
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
    description="List system logs with optional filters for user, action, and date range."
)
@require_permissions([Permission.VIEW_LOGS])
async def read_system_logs_endpoint(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 50,
    request: Request = Depends(),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[SystemLogOut]:
    """
    List system logs with optional filters.

    Args:
        user_id: Optional ID of the user to filter logs (default: None).
        action: Optional action type to filter logs (default: None).
        start_date: Optional start date to filter logs (default: None).
        end_date: Optional end date to filter logs (default: None).
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: 50).
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        settings: Application settings for pagination.

    Returns:
        List[SystemLogOut]: List of system logs matching the filters.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_read_system_logs(user_id, action, start_date, end_date, skip, limit, db, settings, request_id)
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
    description="Retrieve system logs for a specific user, optionally filtered by action."
)
@require_permissions([Permission.VIEW_LOGS])
async def get_user_logs_endpoint(
    user_id: int,
    action: Optional[str] = None,
    limit: int = 100,
    request: Request = Depends(),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[SystemLogOut]:
    """
    Retrieve logs for a specific user.

    Args:
        user_id: The ID of the user to retrieve logs for.
        action: Optional action type to filter logs (default: None).
        limit: Maximum number of records to return (default: 100).
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        settings: Application settings for pagination.

    Returns:
        List[SystemLogOut]: List of system logs for the specified user.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_get_user_logs(user_id, action, limit, db, settings, request_id)
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
    description="Retrieve a summary of system actions, optionally filtered by date range."
)
@require_permissions([Permission.VIEW_LOGS])
async def get_log_actions_summary_endpoint(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    request: Request = Depends(),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[SystemLogActionSummary]:
    """
    Retrieve a summary of system actions.

    Args:
        start_date: Optional start date to filter logs (default: None).
        end_date: Optional end date to filter logs (default: None).
        request: The incoming HTTP request for logging client details.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[SystemLogActionSummary]: A list of action types and their occurrence counts.

    Raises:
        HTTPException: For validation errors (422) or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await service_get_log_actions_summary(start_date, end_date, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving log actions summary: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving log actions summary: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")