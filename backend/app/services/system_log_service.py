from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone
from app.models.system_logs import SystemLogs
from app.models.users import Users
from app.schemas.system_log import SystemLogCreate, SystemLogOut, SystemLogActionSummary
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import UserNotFoundError, ValidationError, DatabaseError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

async def create_system_log(
    log: SystemLogCreate,
    request: Optional[Request] = None,
    current_user: Optional[Users] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.CREATE_LOGS]))
) -> SystemLogOut:
    """
    Create a system log entry with validation and JSON logging."""
    try:
        # Validate user_id if provided
        if log.user_id:
            query = select(Users).where(
                Users.user_id == log.user_id,
                Users.is_active == True,
                Users.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise UserNotFoundError(user_id=log.user_id)

        valid_actions = [action.value for action in SystemAction]
        if log.action.value not in valid_actions:
            raise ValidationError(detail=f"Invalid action. Must be one of: {', '.join(valid_actions)}")

        # Create system log
        db_log = SystemLogs(
            user_id=log.user_id,
            action=log.action.value,
            table_affected=log.table_affected,
            record_id=log.record_id,
            old_values=log.old_values,
            new_values=log.new_values,
            ip_address=request.client.host if request else log.ip_address,
            user_agent=request.headers.get("user-agent") if request else log.user_agent,
            request_id=log.request_id or request_id,
            timestamp=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_log)
        await db.commit()
        await db.refresh(db_log)

        logger.info(
            f"System log created, log_id: {db_log.log_id}, action: {db_log.action}",
            extra={"request_id": db_log.request_id, "user_id": db_log.user_id}
        )
        return SystemLogOut.model_validate(db_log)

    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": log.request_id or request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": log.request_id or request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error creating system log: {str(e)}", extra={"request_id": log.request_id or request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error creating system log: {str(e)}", extra={"request_id": log.request_id or request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def read_system_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_LOGS]))
) -> SystemLogOut:
    """
    Retrieve a system log by ID."""
    try:
        if log_id <= 0:
            raise ValidationError(detail="Invalid log ID")

        query = select(SystemLogs).where(
            SystemLogs.log_id == log_id,
            SystemLogs.is_active == True
        )
        result = await db.execute(query)
        log = result.scalar_one_or_none()

        if not log:
            raise UserNotFoundError(user_id=log_id, detail="System log not found")

        logger.info(
            f"Retrieved system log, log_id: {log_id}",
            extra={"request_id": request_id}
        )
        return SystemLogOut.model_validate(log)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"Log not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving system log {log_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving system log {log_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def read_system_logs(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_LOGS]))
) -> List[SystemLogOut]:
    """
    Retrieve a list of system logs with optional filters and pagination."""
    try:
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")

        if user_id:
            query = select(Users).where(
                Users.user_id == user_id,
                Users.is_active == True,
                Users.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise UserNotFoundError(user_id=user_id)

        if action and action not in [a.value for a in SystemAction]:
            raise ValidationError(detail=f"Invalid action. Must be one of: {[a.value for a in SystemAction]}")

        if start_date and end_date and start_date > end_date:
            raise ValidationError(detail="start_date cannot be later than end_date")

        query = select(SystemLogs).where(SystemLogs.is_active == True)
        if user_id:
            query = query.where(SystemLogs.user_id == user_id)
        if action:
            query = query.where(SystemLogs.action == action)
        if start_date:
            query = query.where(SystemLogs.timestamp >= start_date)
        if end_date:
            query = query.where(SystemLogs.timestamp <= end_date)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        logs = result.scalars().all()

        logger.info(
            f"Retrieved {len(logs)} system logs",
            extra={"request_id": request_id, "user_id": user_id, "action": action}
        )
        return [SystemLogOut.model_validate(log) for log in logs]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving system logs: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving system logs: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_user_logs(
    user_id: int,
    action: Optional[str] = None,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_LOGS]))
) -> List[SystemLogOut]:
    """
    Retrieve system logs for a specific user with optional action filter."""
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user ID")

        if limit is not None and limit <= 0:
            raise ValidationError(detail="Invalid limit parameter")

        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise UserNotFoundError(user_id=user_id)

        if action and action not in [a.value for a in SystemAction]:
            raise ValidationError(detail=f"Invalid action. Must be one of: {[a.value for a in SystemAction]}")

        query = select(SystemLogs).where(
            SystemLogs.user_id == user_id,
            SystemLogs.is_active == True
        )
        if action:
            query = query.where(SystemLogs.action == action)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = query.limit(limit)
        result = await db.execute(query)
        logs = result.scalars().all()

        logger.info(
            f"Retrieved {len(logs)} logs for user_id: {user_id}",
            extra={"request_id": request_id, "action": action}
        )
        return [SystemLogOut.model_validate(log) for log in logs]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving logs for user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving logs for user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_log_actions_summary(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_LOGS]))
) -> List[SystemLogActionSummary]:
    """
    Retrieve a summary of system actions with occurrence counts."""
    try:
        if start_date and end_date and start_date > end_date:
            raise ValidationError(detail="start_date cannot be later than end_date")

        query = select(
            SystemLogs.action,
            func.count(SystemLogs.log_id).label("count")
        ).where(SystemLogs.is_active == True)
        if start_date:
            query = query.where(SystemLogs.timestamp >= start_date)
        if end_date:
            query = query.where(SystemLogs.timestamp <= end_date)

        query = query.group_by(SystemLogs.action)
        result = await db.execute(query)
        summaries = result.all()

        logger.info(
            f"Retrieved action summary with {len(summaries)} actions",
            extra={"request_id": request_id}
        )
        return [SystemLogActionSummary(action=row.action, count=row.count) for row in summaries]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving action summary: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving action summary: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")