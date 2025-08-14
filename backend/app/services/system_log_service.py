from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request, APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.system_logs import SystemLogs
from app.models.users import Users
from app.schemas.system_log import SystemLogCreate, SystemLogOut
from app.core.config import settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import UserNotFoundError, ResourceNotFoundError, ValidationError, DatabaseError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

class SystemLogService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_system_log(
        self,
        log: SystemLogCreate,
        current_user: Optional[Users] = None,
        request: Optional[Request] = None,
        request_id: Optional[str] = None
    ) -> SystemLogOut:
        """
        Create a system log entry with validation and JSON logging.
        """
        try:
            # Validate user_id if provided
            if log.user_id:
                query = select(Users).where(
                    Users.user_id == log.user_id,
                    Users.is_active == True,
                    Users.deleted_at == None
                )
                result = await self.db.execute(query)
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
            self.db.add(db_log)
            await self.db.commit()
            await self.db.refresh(db_log)

            logger.info(f"System log created, log_id: {db_log.log_id}, action: {db_log.action}", extra={"request_id": db_log.request_id})
            return SystemLogOut.model_validate(db_log)

        except HTTPException:
            raise
        except DatabaseError as e:
            logger.error(f"Database error creating system log: {str(e)}", extra={"request_id": log.request_id or request_id})
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating system log: {str(e)}", extra={"request_id": log.request_id or request_id})
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error creating system log"
            )

    async def get_system_log_by_id(self, log_id: int, request_id: Optional[str] = None) -> Optional[SystemLogOut]:
        """
        Retrieve a system log by ID. Requires view_system_log permission.
        """
        try:
            query = select(SystemLogs).where(
                SystemLogs.log_id == log_id,
                SystemLogs.is_active == True
            )
            result = await self.db.execute(query)
            system_log = result.scalar_one_or_none()

            if not system_log:
                raise ResourceNotFoundError(resource="System log", identifier=f"ID {log_id}")

            logger.info(f"Retrieved system log, log_id: {log_id}", extra={"request_id": request_id})
            return SystemLogOut.model_validate(system_log)

        except ResourceNotFoundError:
            raise
        except DatabaseError as e:
            logger.error(f"Database error retrieving system log {log_id}: {str(e)}", extra={"request_id": request_id})
            raise
        except Exception as e:
            logger.error(f"Unexpected error retrieving system log {log_id}: {str(e)}", extra={"request_id": request_id})
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error retrieving system log"
            )

    async def get_system_logs(self, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE, request_id: Optional[str] = None) -> List[SystemLogOut]:
        """
        Retrieve a list of system logs with pagination. Requires view_system_log permission.
        """
        try:
            query = select(SystemLogs).where(
                SystemLogs.is_active == True
            ).offset(skip).limit(limit)
            result = await self.db.execute(query)
            system_logs = result.scalars().all()

            logger.info(f"Retrieved {len(system_logs)} system logs", extra={"request_id": request_id})
            return [SystemLogOut.model_validate(log) for log in system_logs]

        except DatabaseError as e:
            logger.error(f"Database error retrieving system logs: {str(e)}", extra={"request_id": request_id})
            raise
        except Exception as e:
            logger.error(f"Unexpected error retrieving system logs: {str(e)}", extra={"request_id": request_id})
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error retrieving system logs"
            )

    async def get_system_logs_by_user(self, user_id: int, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE, request_id: Optional[str] = None) -> List[SystemLogOut]:
        """
        Retrieve system logs for a specific user with pagination. Requires view_system_log permission.
        """
        try:
            query = select(Users).where(
                Users.user_id == user_id,
                Users.is_active == True,
                Users.deleted_at == None
            )
            result = await self.db.execute(query)
            if not result.scalar_one_or_none():
                raise UserNotFoundError(user_id=user_id)

            query = select(SystemLogs).where(
                SystemLogs.user_id == user_id,
                SystemLogs.is_active == True
            ).offset(skip).limit(limit)
            result = await self.db.execute(query)
            system_logs = result.scalars().all()

            logger.info(f"Retrieved {len(system_logs)} system logs for user_id: {user_id}", extra={"request_id": request_id})
            return [SystemLogOut.model_validate(log) for log in system_logs]

        except HTTPException:
            raise
        except DatabaseError as e:
            logger.error(f"Database error retrieving system logs for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
            raise
        except Exception as e:
            logger.error(f"Unexpected error retrieving system logs for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error retrieving system logs for user"
            )

def get_system_log_service(db: AsyncSession = Depends(get_db)) -> SystemLogService:
    """Dependency to provide SystemLogService instance."""
    return SystemLogService(db)

# API endpoints for system logs
router = APIRouter(prefix="/system-logs", tags=["System Logs"])

@router.post("/", response_model=SystemLogOut, status_code=status.HTTP_201_CREATED)
async def create_log(
    log: SystemLogCreate,
    service: SystemLogService = Depends(get_system_log_service),
    current_user: Users = Depends(get_current_user),
    request: Request = Depends(),
    _: bool = Depends(require_permissions([Permission.CREATE_LOGS]))
):
    """Create a system log entry."""
    request_id = getattr(request.state, "request_id", None)
    return await service.create_system_log(log, current_user, request, request_id)

@router.get("/{log_id}", response_model=SystemLogOut)
@require_permissions([Permission.VIEW_LOGS])
async def get_log(
    log_id: int,
    service: SystemLogService = Depends(get_system_log_service),
    request: Request = Depends()
):
    """Retrieve a system log by ID. Requires VIEW_LOGS permission."""
    request_id = getattr(request.state, "request_id", None)
    return await service.get_system_log_by_id(log_id, request_id)

@router.get("/", response_model=List[SystemLogOut])
@require_permissions([Permission.VIEW_LOGS])
async def list_logs(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    service: SystemLogService = Depends(get_system_log_service),
    request: Request = Depends()
):
    """List system logs with pagination. Requires VIEW_LOGS permission."""
    request_id = getattr(request.state, "request_id", None)
    return await service.get_system_logs(skip, limit, request_id)

@router.get("/user/{user_id}", response_model=List[SystemLogOut])
@require_permissions([Permission.VIEW_LOGS])
async def list_user_logs(
    user_id: int,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    service: SystemLogService = Depends(get_system_log_service),
    request: Request = Depends()
):
    """List system logs for a specific user. Requires VIEW_LOGS permission."""
    request_id = getattr(request.state, "request_id", None)
    return await service.get_system_logs_by_user(user_id, skip, limit, request_id)