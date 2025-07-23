from typing import List, Optional, Dict
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from datetime import datetime, timezone
from app.models.system_logs import SystemLog
from app.models.users import Users
from app.schemas.user import SystemLogCreate, SystemLogOut
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

async def create_system_log(db: AsyncSession, log_create: SystemLogCreate, current_user: Optional[Users] = None) -> SystemLogOut:
    try:
        # Validate action
        valid_actions = [
            "INSERT", "UPDATE", "DELETE", "LOGIN", "LOGOUT", "CLOCK_IN", "CLOCK_OUT",
            "password_change", "profile_update", "data_export", "data_import",
            "assign_role", "revoke_role", "view_report", "approve_leave", "reject_leave",
            "create_department", "delete_department"
        ]
        if log_create.action not in valid_actions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"Invalid action. Must be one of {valid_actions}")
        
        # Validate user_id if provided
        if log_create.user_id:
            query = select(Users).where(Users.user_id == log_create.user_id, 
                                    Users.is_active == True, 
                                    Users.deleted_at == None)
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                                  detail="User not found")
        
        db_log = SystemLog(
            **log_create.model_dump(),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(db_log)
        await db.commit()
        await db.refresh(db_log)
        
        logger.info(f"System log created, log_id {db_log.log_id}, action {db_log.action}")
        return SystemLogOut.model_validate(db_log)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating system log: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error creating system log")

async def get_system_log_by_id(db: AsyncSession, log_id: int, current_user: Users) -> Optional[SystemLogOut]:
    try:
        query = select(SystemLog).where(SystemLog.log_id == log_id)
        result = await db.execute(query)
        system_log = result.scalar_one_or_none()
        
        if not system_log:
            return None
        
        # Check permission to view logs
        from app.services.auth_service import check_user_permission
        has_permission = await check_user_permission(db, current_user.user_id, "view_system_logs")
        if not has_permission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                              detail="Not authorized to view system logs")
        
        return SystemLogOut.model_validate(system_log)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving system log: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error retrieving system log")

async def get_system_logs(db: AsyncSession, user_id: Optional[int] = None, 
                        action: Optional[str] = None, 
                        start_date: Optional[datetime] = None, 
                        end_date: Optional[datetime] = None, 
                        skip: int = 0, 
                        limit: int = settings.DEFAULT_PAGE_SIZE, 
                        current_user: Optional[Users] = None) -> List[SystemLogOut]:
    try:
        # Check permission to view logs
        from app.services.auth_service import check_user_permission
        if current_user:
            has_permission = await check_user_permission(db, current_user.user_id, "view_system_logs")
            if not has_permission:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                                  detail="Not authorized to view system logs")
        
        query = select(SystemLog)
        
        if user_id:
            query = query.where(SystemLog.user_id == user_id)
        
        if action:
            valid_actions = [
                "INSERT", "UPDATE", "DELETE", "LOGIN", "LOGOUT", "CLOCK_IN", "CLOCK_OUT",
                "password_change", "profile_update", "data_export", "data_import",
                "assign_role", "revoke_role", "view_report", "approve_leave", "reject_leave",
                "create_department", "delete_department"
            ]
            if action not in valid_actions:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                                  detail=f"Invalid action. Must be one of {valid_actions}")
            query = query.where(SystemLog.action == action)
        
        if start_date:
            query = query.where(SystemLog.timestamp >= start_date)
        
        if end_date:
            query = query.where(SystemLog.timestamp <= end_date)
        
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        system_logs = result.scalars().all()
        
        logger.info(f"Retrieved {len(system_logs)} system logs")
        return [SystemLogOut.model_validate(log) for log in system_logs]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving system logs: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error retrieving system logs")