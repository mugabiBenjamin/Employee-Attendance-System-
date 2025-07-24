from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict
from app.models.system_logs import SystemLogs
from app.models.users import Users
from app.schemas.system_log import SystemLogCreate, SystemLogOut
from app.core.config import settings
from app.core.enums import SystemAction
import logging

logger = logging.getLogger(__name__)

class SystemLogCreateInternal(BaseModel):
    user_id: Optional[int] = None
    action: SystemAction
    table_affected: Optional[str] = None
    record_id: Optional[int] = None
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    ip_address: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

async def create_system_log(db: AsyncSession, log: SystemLogCreate, current_user: Optional[Users] = None) -> SystemLogOut:
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
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )

        # Create system log
        db_log = SystemLogs(
            **SystemLogCreateInternal(**log.model_dump()).model_dump(),
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

async def get_system_log_by_id(db: AsyncSession, log_id: int) -> Optional[SystemLogOut]:
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
            return None

        return SystemLogOut.model_validate(system_log)

    except Exception as e:
        logger.error(f"Error retrieving system log {log_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving system log"
        )

async def get_system_logs(db: AsyncSession, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[SystemLogOut]:
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

async def get_system_logs_by_user(db: AsyncSession, user_id: int, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[SystemLogOut]:
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

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