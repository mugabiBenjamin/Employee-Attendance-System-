from typing import List, Optional
from fastapi import HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.system_logs import SystemLogs
from app.models.users import Users
from app.schemas.system_log import SystemLogCreate, SystemLogOut
from app.core.config import settings
from app.core.enums import SystemAction
from app.core.exceptions import UserNotFoundError
from app.core.security import get_current_user
from app.core.permissions import check_permission
import logging

logger = logging.getLogger(__name__)

async def create_system_log(
    db: AsyncSession,
    log: SystemLogCreate,
    current_user: Optional[Users] = Depends(get_current_user)
) -> SystemLogOut:
    """
    Create a system log entry with validation and logging.
    """
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
                raise UserNotFoundError(detail="User not found")

        # Validate action
        if log.action not in SystemAction.__members__:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid action. Must be one of: {', '.join(SystemAction.__members__)}"
            )

        # Create system log
        db_log = SystemLogs(
            user_id=log.user_id,
            action=log.action,
            table_affected=log.table_affected,
            record_id=log.record_id,
            old_values=log.old_values,
            new_values=log.new_values,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(db_log)
        await db.commit()
        await db.refresh(db_log)

        logger.info(f"System log created, log_id: {db_log.log_id}, action: {db_log.action}")
        return SystemLogOut.model_validate(db_log)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating system log: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating system log"
        )

async def get_system_log_by_id(
    db: AsyncSession,
    log_id: int,
    _: str = Depends(check_permission("view_system_log"))
) -> Optional[SystemLogOut]:
    """
    Retrieve a system log by ID.
    """
    try:
        query = select(SystemLogs).where(
            SystemLogs.log_id == log_id
        )
        result = await db.execute(query)
        system_log = result.scalar_one_or_none()

        if not system_log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="System log not found"
            )

        return SystemLogOut.model_validate(system_log)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving system log {log_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving system log"
        )

async def get_system_logs(
    db: AsyncSession,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    _: str = Depends(check_permission("view_system_log"))
) -> List[SystemLogOut]:
    """
    Retrieve a list of system logs with pagination.
    """
    try:
        query = select(SystemLogs).offset(skip).limit(limit)
        result = await db.execute(query)
        system_logs = result.scalars().all()

        logger.info(f"Retrieved {len(system_logs)} system logs")
        return [SystemLogOut.model_validate(log) for log in system_logs]

    except Exception as e:
        logger.error(f"Error retrieving system logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving system logs"
        )

async def get_system_logs_by_user(
    db: AsyncSession,
    user_id: int,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    _: str = Depends(check_permission("view_system_log"))
) -> List[SystemLogOut]:
    """
    Retrieve system logs for a specific user with pagination.
    """
    try:
        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise UserNotFoundError(detail="User not found")

        query = select(SystemLogs).where(
            SystemLogs.user_id == user_id
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        system_logs = result.scalars().all()

        logger.info(f"Retrieved {len(system_logs)} system logs for user_id: {user_id}")
        return [SystemLogOut.model_validate(log) for log in system_logs]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving system logs for user_id {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving system logs for user"
        )