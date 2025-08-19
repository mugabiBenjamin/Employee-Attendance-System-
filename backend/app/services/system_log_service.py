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
from app.core.exceptions import UserNotFoundError, SystemLogNotFoundError, ValidationError, DepartmentNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_user_exists, validate_department_exists
import logging

logger = logging.getLogger(__name__)

async def create_system_log(
    log: SystemLogCreate,
    request: Optional[Request] = None,
    current_user: Optional[Users] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None
) -> SystemLogOut:
    """Create a system log entry with validation and JSON logging."""
    try:
        # Validate user_id if provided
        if log.user_id:
            await validate_user_exists(db, log.user_id, request_id)

        # Validate table_affected
        if log.table_affected and not log.table_affected.isidentifier():
            raise ValidationError(detail="Invalid table name")

        # Create system log
        db_log = SystemLogs(
            user_id=log.user_id,
            action=log.action.value,
            table_affected=log.table_affected,
            record_id=log.record_id,
            old_values=log.old_values,
            new_values=log.new_values,
            ip_address=str(log.ip_address) if log.ip_address else (str(request.client.host) if request else None),
            user_agent=log.user_agent or (request.headers.get("user-agent") if request else None),
            request_id=log.request_id or request_id,
            timestamp=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_log)
        await db.commit()
        await db.refresh(db_log)

        # Invalidate cache
        await invalidate_cache_prefix("system_log")
        logger.debug(f"Cache cleared for system_log")

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
    except Exception as e:
        logger.error(f"Error creating system log: {str(e)}", extra={"request_id": log.request_id or request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating system log")

async def read_system_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_LOGS]))
) -> SystemLogOut:
    """Retrieve a system log by ID."""
    try:
        if log_id <= 0:
            raise ValidationError(detail="Invalid log ID")

        cache_key = f"system_log:{log_id}"
        cached_log = await get_cache(cache_key)
        if cached_log:
            return SystemLogOut(**cached_log)

        query = select(SystemLogs).where(
            SystemLogs.log_id == log_id,
            SystemLogs.is_active == True,
            SystemLogs.deleted_at == None
        )
        result = await db.execute(query)
        log = result.scalar_one_or_none()

        if not log:
            raise SystemLogNotFoundError(log_id=log_id)

        log_dict = SystemLogOut.model_validate(log).model_dump()
        await set_cache(cache_key, log_dict, ttl=300)

        logger.info(
            f"Retrieved system log, log_id: {log_id}",
            extra={"request_id": request_id}
        )
        return SystemLogOut.model_validate(log)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SystemLogNotFoundError as e:
        logger.error(f"Log not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving system log {log_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving system log")

async def read_system_logs(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    department_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_LOGS]))
) -> List[SystemLogOut]:
    """Retrieve a list of system logs with optional filters and pagination."""
    try:
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")

        if user_id:
            await validate_user_exists(db, user_id, request_id)

        if action and action not in [a.value for a in SystemAction]:
            raise ValidationError(detail=f"Invalid action. Must be one of: {[a.value for a in SystemAction]}")

        if start_date and end_date and start_date > end_date:
            raise ValidationError(detail="start_date cannot be later than end_date")

        cache_key = f"system_logs:{user_id or 'all'}:{action or 'all'}:{department_id or 'all'}:{start_date or 'none'}:{end_date or 'none'}:{skip}:{limit or settings.DEFAULT_PAGE_SIZE}"
        cached_logs = await get_cache(cache_key)
        if cached_logs:
            return [SystemLogOut(**log) for log in cached_logs]

        query = select(SystemLogs).where(
            SystemLogs.is_active == True,
            SystemLogs.deleted_at == None
        )
        if user_id:
            query = query.where(SystemLogs.user_id == user_id)
        if action:
            query = query.where(SystemLogs.action == action)
        if department_id:
            from app.models.user_departments import UserDepartments
            await validate_department_exists(db, department_id, request_id)
            query = query.join(UserDepartments, UserDepartments.user_id == SystemLogs.user_id).where(
                UserDepartments.department_id == department_id,
                UserDepartments.is_active == True,
                UserDepartments.deleted_at == None
            )
        if start_date:
            query = query.where(SystemLogs.timestamp >= start_date)
        if end_date:
            query = query.where(SystemLogs.timestamp <= end_date)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        logs = result.scalars().all()

        logs_dict = [SystemLogOut.model_validate(log).model_dump() for log in logs]
        await set_cache(cache_key, logs_dict, ttl=300)

        logger.info(
            f"Retrieved {len(logs)} system logs",
            extra={"request_id": request_id, "user_id": user_id, "action": action, "department_id": department_id}
        )
        return [SystemLogOut.model_validate(log) for log in logs]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (UserNotFoundError, DepartmentNotFoundError) as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving system logs: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving system logs")

async def get_user_logs(
    user_id: int,
    action: Optional[str] = None,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_LOGS]))
) -> List[SystemLogOut]:
    """Retrieve system logs for a specific user with optional action filter."""
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user ID")

        if limit is not None and limit <= 0:
            raise ValidationError(detail="Invalid limit parameter")

        await validate_user_exists(db, user_id, request_id)

        if action and action not in [a.value for a in SystemAction]:
            raise ValidationError(detail=f"Invalid action. Must be one of: {[a.value for a in SystemAction]}")

        cache_key = f"user_logs:{user_id}:{action or 'all'}:{limit or settings.DEFAULT_PAGE_SIZE}"
        cached_logs = await get_cache(cache_key)
        if cached_logs:
            return [SystemLogOut(**log) for log in cached_logs]

        query = select(SystemLogs).where(
            SystemLogs.user_id == user_id,
            SystemLogs.is_active == True,
            SystemLogs.deleted_at == None
        )
        if action:
            query = query.where(SystemLogs.action == action)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = query.limit(limit)
        result = await db.execute(query)
        logs = result.scalars().all()

        logs_dict = [SystemLogOut.model_validate(log).model_dump() for log in logs]
        await set_cache(cache_key, logs_dict, ttl=300)

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
    except Exception as e:
        logger.error(f"Error retrieving logs for user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving logs")

async def get_log_actions_summary(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_LOGS]))
) -> List[SystemLogActionSummary]:
    """Retrieve a summary of system actions with occurrence counts."""
    try:
        if start_date and end_date and start_date > end_date:
            raise ValidationError(detail="start_date cannot be later than end_date")

        cache_key = f"log_actions_summary:{start_date or 'none'}:{end_date or 'none'}"
        cached_summary = await get_cache(cache_key)
        if cached_summary:
            return [SystemLogActionSummary(**s) for s in cached_summary]

        query = select(
            SystemLogs.action,
            func.count(SystemLogs.log_id).label("count")
        ).where(
            SystemLogs.is_active == True,
            SystemLogs.deleted_at == None
        )
        if start_date:
            query = query.where(SystemLogs.timestamp >= start_date)
        if end_date:
            query = query.where(SystemLogs.timestamp <= end_date)

        query = query.group_by(SystemLogs.action)
        result = await db.execute(query)
        summaries = result.all()

        summaries_dict = [SystemLogActionSummary(action=row.action, count=row.count).model_dump() for row in summaries]
        await set_cache(cache_key, summaries_dict, ttl=300)

        logger.info(
            f"Retrieved action summary with {len(summaries)} actions",
            extra={"request_id": request_id}
        )
        return [SystemLogActionSummary(action=row.action, count=row.count) for row in summaries]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving action summary: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving action summary")

async def delete_system_log(
    log_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.DELETE_LOGS]))
) -> None:
    """Soft delete a system log with logging and cache clearing."""
    try:
        if log_id <= 0:
            raise ValidationError(detail="Invalid log ID")

        query = select(SystemLogs).where(
            SystemLogs.log_id == log_id,
            SystemLogs.is_active == True,
            SystemLogs.deleted_at == None
        )
        result = await db.execute(query)
        db_log = result.scalar_one_or_none()

        if not db_log:
            raise SystemLogNotFoundError(log_id=log_id)

        db_log.is_active = False
        db_log.deleted_at = datetime.now(timezone.utc)
        db.add(db_log)
        await db.commit()

        # Invalidate cache
        await invalidate_cache_prefix("system_log")
        logger.debug(f"Cache cleared for system_log")

        # Log the deletion
        delete_log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_SYSTEM_LOG,
            table_affected="system_logs",
            record_id=log_id,
            old_values=db_log.__dict__,
            new_values=None,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(delete_log, request, current_user, db, settings, request_id)

        logger.info(
            f"System log soft deleted, log_id: {log_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SystemLogNotFoundError as e:
        logger.error(f"Log not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting system log {log_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting system log")