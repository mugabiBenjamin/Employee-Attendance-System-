from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import AsyncGenerator, List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone
from app.core.database import AsyncSessionLocal
from app.models.system_logs import SystemLogs
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.core.config import settings
from app.core.permissions import check_permissions
from app.core.security import get_current_active_user
from app.core.enums import Permission
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system-logs", tags=["System Logs"])

class SystemLogOut(BaseModel):
    """Schema for system log output."""
    log_id: int
    user_id: Optional[int]
    action: str
    entity_type: str
    entity_id: Optional[int]
    details: Optional[str]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to provide an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {str(e)}")
            await session.rollback()
            raise
        finally:
            await session.close()

async def is_admin_or_hr(db: AsyncSession, user: Users) -> bool:
    """Check if user has HR, Admin, or Super_Admin role."""
    try:
        query = select(UserRoles).join(Roles).where(
            UserRoles.user_id == user.user_id,
            UserRoles.is_active == True,
            Roles.role_name.in_(["HR", "Admin", "Super_Admin"]),
            Roles.is_active == True
        )
        result = await db.execute(query)
        return result.scalar_one_or_none() is not None
    except Exception as e:
        logger.error(f"Error checking admin/hr role for user_id {user.user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error checking user role")

@router.get("/", response_model=List[SystemLogOut], summary="List system logs")
async def read_system_logs(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[SystemLogOut]:
    """Get a paginated list of all system logs."""
    try:
        has_permission = await check_permissions([Permission.VIEW_SYSTEM_LOGS.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view system logs")

        query = select(SystemLogs).where(SystemLogs.is_active == True).offset(skip).limit(limit)
        result = await db.execute(query)
        logs = result.scalars().all()

        logger.info(f"Retrieved {len(logs)} system logs")
        return [SystemLogOut.model_validate(log) for log in logs]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving system logs: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving system logs")

@router.get("/{log_id}", response_model=SystemLogOut, summary="Get system log by ID")
async def read_system_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> SystemLogOut:
    """Get a specific system log by ID."""
    try:
        has_permission = await check_permissions([Permission.VIEW_SYSTEM_LOGS.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view system logs")

        query = select(SystemLogs).where(SystemLogs.log_id == log_id, SystemLogs.is_active == True)
        result = await db.execute(query)
        log = result.scalar_one_or_none()

        if not log:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="System log not found")

        logger.info(f"Retrieved system log, log_id: {log_id}")
        return SystemLogOut.model_validate(log)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving system log {log_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving system log")