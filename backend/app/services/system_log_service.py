from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.models.system_logs import SystemLogs
from app.models.users import Users
from app.models.user_departments import UserDepartments
from app.models.employee_hierarchy import EmployeeHierarchy
from app.schemas.system_log import SystemLogCreate, SystemLogOut, SystemLogActionSummary
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import UserNotFoundError, SystemLogNotFoundError, ValidationError, DepartmentNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions_dependency, invalidate_user_cache, get_user_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_user_exists, validate_department_exists
from app.core.utils import get_request_id, get_users_with_permission
from app.core.mail import send_email
import logging
import json

logger = logging.getLogger(__name__)

async def _check_user_authorization(
    db: AsyncSession,
    current_user: Users,
    target_user_id: int,
    required_permissions: List[Permission],
    request_id: Optional[str] = None
) -> bool:
    """Check if the current user is authorized to perform actions on the target user's logs."""
    user_permissions = await get_user_permissions(current_user.user_id, db)
    if target_user_id == current_user.user_id or any(p.value in user_permissions for p in required_permissions):
        return True
    query_hierarchy = select(EmployeeHierarchy).where(
        EmployeeHierarchy.employee_id == target_user_id,
        EmployeeHierarchy.supervisor_id == current_user.user_id,
        EmployeeHierarchy.is_active.is_(True),
        EmployeeHierarchy.deleted_at.is_(None)
    )
    result_hierarchy = await db.execute(query_hierarchy)
    return bool(result_hierarchy.scalar_one_or_none())

async def create_system_log(
    log: SystemLogCreate,
    request: Optional[Request] = None,
    current_user: Optional[Users] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id)
) -> SystemLogOut:
    """Create a system log entry with validation and JSON logging."""
    try:
        # Validate user_id if provided
        if log.user_id:
            if log.user_id <= 0:
                raise ValidationError(detail="Invalid user ID")
            await validate_user_exists(db, log.user_id, request_id)

        # Validate table_affected
        if log.table_affected and not log.table_affected.isidentifier():
            raise ValidationError(detail="Invalid table name")

        # Validate action
        if log.action not in [a.value for a in SystemAction]:
            raise ValidationError(detail=f"Invalid action. Must be one of: {[a.value for a in SystemAction]}")

        # Validate JSON-serializable old_values and new_values
        if log.old_values:
            try:
                json.dumps(log.old_values)
            except (TypeError, ValueError):
                raise ValidationError(detail="old_values must be JSON-serializable")
        if log.new_values:
            try:
                json.dumps(log.new_values)
            except (TypeError, ValueError):
                raise ValidationError(detail="new_values must be JSON-serializable")

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
        logger.debug(f"db_log after commit: {db_log.__dict__}", extra={"request_id": request_id})

        if db_log is not None and hasattr(db_log, 'log_id'):
            try:
                await db.refresh(db_log)
                logger.debug(f"db_log after refresh: {db_log.__dict__}", extra={"request_id": request_id})
            except Exception as refresh_error:
                logger.warning(f"Failed to refresh db_log, but continuing: {str(refresh_error)}", extra={"request_id": request_id})
        else:
            logger.error(f"db_log is None or missing log_id after commit", extra={"request_id": request_id})
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create system log: Invalid log object"
            )

        # Check if db_log is valid
        if db_log.log_id is None:
            logger.error(f"System log creation failed, log_id is None", extra={"request_id": request_id})
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create system log: No log_id assigned"
            )

        # Invalidate cache
        await invalidate_cache_prefix("system_log")
        logger.info(f"Cache invalidated for system_log", extra={"request_id": request_id})

        logger.info(
            f"System log created, log_id: {db_log.log_id}, action: {db_log.action}, user_id: {db_log.user_id or 'none'}",
            extra={"request_id": request_id, "user_id": db_log.user_id}
        )
        return SystemLogOut.model_validate(db_log)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating system log: {str(e)}", extra={"request_id": request_id})
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating system log")

async def read_system_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_LOGS]))
) -> SystemLogOut:
    """Retrieve a system log by ID."""
    try:
        if log_id <= 0:
            raise ValidationError(detail="Invalid log ID")

        cache_key = f"system_log:{log_id}"
        cached_log = await get_cache(cache_key)
        if cached_log:
            logger.info(f"Cache hit for system_log:{log_id}", extra={"request_id": request_id})
            return SystemLogOut(**cached_log)

        query = select(SystemLogs).where(
            SystemLogs.log_id == log_id,
            SystemLogs.is_active.is_(True),
            SystemLogs.deleted_at.is_(None)
        )
        result = await db.execute(query)
        log = result.scalar_one_or_none()

        if not log:
            raise SystemLogNotFoundError(log_id=log_id)

        log_output = SystemLogOut.model_validate(log)
        log_dict = log_output.model_dump(mode='json')
        await set_cache(cache_key, log_dict, ttl=300)
        logger.info(f"Cache set for system_log:{log_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved system log, log_id: {log_id}",
            extra={"request_id": request_id}
        )
        return log_output

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SystemLogNotFoundError as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving system log {log_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving system log")

async def read_system_logs(
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
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_LOGS]))
) -> List[SystemLogOut]:
    """Retrieve a list of system logs with optional filters and pagination."""
    try:
        if user_id and department_id:
            raise ValidationError(detail="Cannot specify both user_id and department_id")
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")
        if start_date and end_date and start_date > end_date:
            raise ValidationError(detail="start_date cannot be later than end_date")
        if user_id and user_id <= 0:
            raise ValidationError(detail="Invalid user ID")
        if action and action not in [a.value for a in SystemAction]:
            raise ValidationError(detail=f"Invalid action. Must be one of: {[a.value for a in SystemAction]}")
        if table_affected and not table_affected.isidentifier():
            raise ValidationError(detail="Invalid table name")

        # Authorization check for user_id
        if user_id and not await _check_user_authorization(db, current_user, user_id, [Permission.VIEW_LOGS, Permission.MANAGE_EMPLOYEES], request_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view logs for this user"
            )

        cache_key = f"system_logs:{user_id or 'all'}:{action or 'all'}:{table_affected or 'all'}:{department_id or 'all'}:{start_date or 'none'}:{end_date or 'none'}:{is_active or 'all'}:{skip}:{limit or settings.DEFAULT_PAGE_SIZE}"
        cached_logs = await get_cache(cache_key)
        if cached_logs:
            logger.info(f"Cache hit for {cache_key}", extra={"request_id": request_id})
            return [SystemLogOut(**log) for log in cached_logs]

        query = select(SystemLogs)
        if is_active is not None:
            query = query.where(SystemLogs.is_active.is_(is_active))
        else:
            query = query.where(SystemLogs.is_active.is_(True), SystemLogs.deleted_at.is_(None))

        if user_id:
            await validate_user_exists(db, user_id, request_id)
            query = query.where(SystemLogs.user_id == user_id)
        if action:
            query = query.where(SystemLogs.action == action)
        if table_affected:
            query = query.where(SystemLogs.table_affected == table_affected)
        if department_id:
            await validate_department_exists(db, department_id, request_id)
            query = query.join(
                UserDepartments,
                and_(
                    UserDepartments.user_id == SystemLogs.user_id,
                    UserDepartments.department_id == department_id,
                    UserDepartments.is_active.is_(True),
                    UserDepartments.deleted_at.is_(None)
                )
            )
        if start_date:
            query = query.where(SystemLogs.timestamp >= start_date)
        if end_date:
            query = query.where(SystemLogs.timestamp <= end_date)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = query.order_by(SystemLogs.log_id.asc()).offset(skip).limit(limit)
        result = await db.execute(query)
        logs = result.scalars().all()

        log_outputs = [SystemLogOut.model_validate(log) for log in logs]
        logs_dict = [log.model_dump(mode='json') for log in log_outputs]
        await set_cache(cache_key, logs_dict, ttl=300)
        logger.info(f"Cache set for {cache_key}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(logs)} system logs for user_id: {user_id or 'all'}, action: {action or 'all'}, department_id: {department_id or 'all'}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return log_outputs

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (UserNotFoundError, DepartmentNotFoundError) as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error retrieving system logs: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving system logs: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving system logs")

async def get_user_logs(
    user_id: int,
    action: Optional[str] = None,
    table_affected: Optional[str] = None,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_LOGS]))
) -> List[SystemLogOut]:
    """Retrieve system logs for a specific user - refactored to use read_system_logs."""
    return await read_system_logs(
        user_id=user_id,
        action=action,
        table_affected=table_affected,
        limit=limit,
        current_user=current_user,
        db=db,
        settings=settings,
        request_id=request_id
    )

async def get_log_actions_summary(
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_LOGS]))
) -> List[SystemLogActionSummary]:
    """Retrieve a summary of system actions with occurrence counts."""
    try:
        if user_id and department_id:
            raise ValidationError(detail="Cannot specify both user_id and department_id")
        if start_date and end_date and start_date > end_date:
            raise ValidationError(detail="start_date cannot be later than end_date")
        if user_id and user_id <= 0:
            raise ValidationError(detail="Invalid user ID")

        cache_key = f"log_actions_summary:{user_id or 'all'}:{department_id or 'all'}:{start_date or 'none'}:{end_date or 'none'}"
        cached_summary = await get_cache(cache_key)
        if cached_summary:
            logger.info(f"Cache hit for {cache_key}", extra={"request_id": request_id})
            return [SystemLogActionSummary(**s) for s in cached_summary]

        query = select(
            SystemLogs.action,
            func.count(SystemLogs.log_id).label("count")
        ).where(
            SystemLogs.is_active.is_(True),
            SystemLogs.deleted_at.is_(None)
        )
        if user_id:
            await validate_user_exists(db, user_id, request_id)
            query = query.where(SystemLogs.user_id == user_id)
        if department_id:
            await validate_department_exists(db, department_id, request_id)
            query = query.join(
                UserDepartments,
                and_(
                    UserDepartments.user_id == SystemLogs.user_id,
                    UserDepartments.department_id == department_id,
                    UserDepartments.is_active.is_(True),
                    UserDepartments.deleted_at.is_(None)
                )
            )
        if start_date:
            query = query.where(SystemLogs.timestamp >= start_date)
        if end_date:
            query = query.where(SystemLogs.timestamp <= end_date)

        query = query.group_by(SystemLogs.action).order_by(SystemLogs.action.asc())
        result = await db.execute(query)
        summaries = result.all()

        summary_outputs = [SystemLogActionSummary(action=row[0], count=row[1]) for row in summaries]
        summaries_dict = [summary.model_dump(mode='json') for summary in summary_outputs]
        await set_cache(cache_key, summaries_dict, ttl=300)
        logger.info(f"Cache set for {cache_key}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved action summary with {len(summaries)} actions for user_id: {user_id or 'all'}, department_id: {department_id or 'all'}",
            extra={"request_id": request_id}
        )
        return summary_outputs

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (UserNotFoundError, DepartmentNotFoundError) as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving action summary: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving action summary")

async def delete_system_log(
    log_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.DELETE_LOGS]))
) -> None:
    """Soft delete a system log with logging and cache clearing."""
    try:
        if log_id <= 0:
            raise ValidationError(detail="Invalid log ID")

        query = select(SystemLogs).where(
            SystemLogs.log_id == log_id,
            SystemLogs.is_active.is_(True),
            SystemLogs.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_log = result.scalar_one_or_none()

        if not db_log:
            raise SystemLogNotFoundError(log_id=log_id)

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if not any(p in [Permission.DELETE_LOGS.value, Permission.MANAGE_EMPLOYEES.value] for p in user_permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete system logs"
            )

        old_values = db_log.__dict__.copy()
        db_log.is_active = False
        db_log.deleted_at = datetime.now(timezone.utc)
        db.add(db_log)
        await db.commit()

        # Invalidate cache
        if db_log.user_id:
            await invalidate_user_cache(db_log.user_id)
        await invalidate_cache_prefix("system_log")
        logger.info(f"Cache invalidated for system_log and user:{db_log.user_id or 'none'}", extra={"request_id": request_id})

        # Notify admins
        await _notify_admins_of_log_deletion(db, db_log, current_user, request_id, settings)

        # Log the deletion
        delete_log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_SYSTEM_LOG,
            table_affected="system_logs",
            record_id=log_id,
            old_values=old_values,
            new_values=None,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(delete_log, request, current_user, db, settings, request_id)

        logger.info(
            f"System log soft deleted, log_id: {log_id}, user_id: {current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SystemLogNotFoundError as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error deleting system log {log_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting system log {log_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting system log")

async def _notify_admins_of_log_deletion(
    db: AsyncSession,
    log: SystemLogs,
    current_user: Users,
    request_id: Optional[str],
    settings: Settings
) -> None:
    """Send notification email to admins about system log deletion."""
    try:
        eat_tz = ZoneInfo("Africa/Nairobi")
        current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
        admins = await get_users_with_permission(Permission.MANAGE_EMPLOYEES, db)
        recipients = [(admin.email, admin.first_name) for admin in admins if admin.email]

        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"System Log Deleted (ID: {log.log_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"A system log has been deleted by {current_user.first_name} {current_user.last_name} ({current_user.email}).\n\n"
                    f"Details:\n"
                    f"Log ID: {log.log_id}\n"
                    f"Action: {log.action}\n"
                    f"Table Affected: {log.table_affected or 'N/A'}\n"
                    f"Record ID: {log.record_id or 'N/A'}\n"
                    f"User ID: {log.user_id or 'N/A'}\n"
                    f"Deleted At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )
        logger.info(
            f"Sent notifications to {len(recipients)} admins for system log deletion, log_id={log.log_id}",
            extra={"request_id": request_id}
        )
    except Exception as e:
        logger.error(
            f"Failed to send notifications for system log deletion, log_id={log.log_id}: {str(e)}",
            extra={"request_id": request_id}
        )