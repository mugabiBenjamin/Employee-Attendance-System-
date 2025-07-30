from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional
from datetime import datetime
from app.core.database import get_db
from app.models.system_logs import SystemLogs
from app.models.users import Users
from app.core.config import settings
from app.core.permissions import check_permissions
from app.core.security import get_current_active_user
from app.core.enums import Permission
from app.schemas.system_log import SystemLogOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system-logs", tags=["System Logs"])

@router.get("/", response_model=List[SystemLogOut], summary="List system logs")
async def read_system_logs(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[SystemLogOut]:
    """List system logs with optional filters. Requires VIEW_LOGS permission."""
    try:
        await check_permissions([Permission.VIEW_LOGS.value], current_user, db)

        query = select(SystemLogs).where(SystemLogs.is_active == True)
        
        # Apply filters
        if user_id:
            query = query.where(SystemLogs.user_id == user_id)
        if action:
            query = query.where(SystemLogs.action == action)
        if start_date:
            query = query.where(SystemLogs.timestamp >= start_date)
        if end_date:
            query = query.where(SystemLogs.timestamp <= end_date)
        
        # Order by most recent first
        query = query.order_by(desc(SystemLogs.timestamp)).offset(skip).limit(limit)
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
    """Get a specific system log by ID. Requires VIEW_LOGS permission."""
    try:
        await check_permissions([Permission.VIEW_LOGS.value], current_user, db)

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

# Additional endpoints for log analysis
@router.get("/user/{user_id}/logs", response_model=List[SystemLogOut], summary="Get logs for specific user")
async def get_user_logs(
    user_id: int,
    action: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[SystemLogOut]:
    """Get system logs for a specific user. Requires VIEW_LOGS permission or viewing own logs."""
    try:
        # Allow users to view their own logs
        if current_user.user_id != user_id:
            await check_permissions([Permission.VIEW_LOGS.value], current_user, db)

        query = select(SystemLogs).where(
            SystemLogs.user_id == user_id,
            SystemLogs.is_active == True
        )
        
        if action:
            query = query.where(SystemLogs.action == action)
        
        query = query.order_by(desc(SystemLogs.timestamp)).limit(limit)
        result = await db.execute(query)
        logs = result.scalars().all()

        return [SystemLogOut.model_validate(log) for log in logs]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving logs for user {user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving user logs")

@router.get("/actions/summary", summary="Get log action summary")
async def get_log_actions_summary(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
):
    """Get summary of system actions. Requires VIEW_LOGS permission."""
    try:
        await check_permissions([Permission.VIEW_LOGS.value], current_user, db)

        query = select(SystemLogs.action, SystemLogs.log_id).where(SystemLogs.is_active == True)
        
        if start_date:
            query = query.where(SystemLogs.timestamp >= start_date)
        if end_date:
            query = query.where(SystemLogs.timestamp <= end_date)
            
        result = await db.execute(query)
        logs = result.all()
        
        # Count actions
        action_counts = {}
        for log in logs:
            action = log.action
            action_counts[action] = action_counts.get(action, 0) + 1
        
        return {
            "total_logs": len(logs),
            "action_summary": action_counts,
            "period": {
                "start_date": start_date,
                "end_date": end_date
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating log summary: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error generating log summary")