from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from app.api.deps import get_db
from app.models.system_logs import SystemLog
from app.services.auth_service import check_user_permission
from app.schemas.system_logs import SystemLogResponse
from app.core.security import get_current_user
from app.models.users import Users

router = APIRouter()

class SystemLogFilter(BaseModel):
    user_id: Optional[int] = None
    action: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    skip: int = 0
    limit: int = 100

@router.get("/logs", response_model=List[SystemLogResponse])
async def get_system_logs(
    filters: SystemLogFilter = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    """Retrieve system logs with optional filters, accessible only to Admin or Super_Admin."""
    # Check if user has Admin or Super_Admin role
    if not await check_user_permission(current_user, ["Admin", "Super_Admin"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view system logs"
        )

    # Build query
    query = select(SystemLog)
    
    # Apply filters
    if filters.user_id:
        query = query.filter(SystemLog.user_id == filters.user_id)
    if filters.action:
        query = query.filter(SystemLog.action == filters.action)
    if filters.start_time:
        query = query.filter(SystemLog.timestamp >= filters.start_time)
    if filters.end_time:
        query = query.filter(SystemLog.timestamp <= filters.end_time)
    
    # Add pagination
    query = query.offset(filters.skip).limit(filters.limit)
    
    # Execute query
    result = await db.execute(query)
    logs = result.scalars().all()
    
    if not logs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No system logs found"
        )
    
    return logs

@router.get("/logs/{log_id}", response_model=SystemLogResponse)
async def get_system_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    """Retrieve a specific system log by ID, accessible only to Admin or Super_Admin."""
    # Check if user has Admin or Super_Admin role
    if not await check_user_permission(current_user, ["Admin", "Super_Admin"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view system logs"
        )

    # Query specific log
    query = select(SystemLog).filter(SystemLog.log_id == log_id)
    result = await db.execute(query)
    log = result.scalar_one_or_none()
    
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"System log with ID {log_id} not found"
        )
    
    return log