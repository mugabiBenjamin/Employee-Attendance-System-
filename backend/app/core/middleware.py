from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.enums import SystemAction
from app.models.system_logs import SystemLogs
import logging

logger = logging.getLogger(__name__)

def setup_middleware(app: FastAPI) -> None:
    """Setup middleware for logging system actions."""
    
    @app.middleware("http")
    async def log_system_actions(request: Request, call_next):
        response = await call_next(request)
        user_id = None
        action = None
        
        # Determine the action based on request method and path
        path = request.url.path
        method = request.method
        
        if path.endswith("/auth/token") and method == "POST":
            action = SystemAction.LOGIN
        elif path.endswith("/auth/logout") and method == "POST":
            action = SystemAction.LOGOUT
        elif path.endswith("/attendance/clock_in") and method == "POST":
            action = SystemAction.CLOCK_IN
        elif path.endswith("/attendance/clock_out") and method == "POST":
            action = SystemAction.CLOCK_OUT
        elif path.endswith("/users/password") and method == "PUT":
            action = SystemAction.PASSWORD_CHANGE
        elif path.endswith("/users/me") and method == "PUT":
            action = SystemAction.PROFILE_UPDATE
        elif path.endswith("/users/export") and method == "GET":
            action = SystemAction.DATA_EXPORT
        elif path.endswith("/users/import") and method == "POST":
            action = SystemAction.DATA_IMPORT
        elif path.endswith("/users/roles") and method == "POST":
            action = SystemAction.ASSIGN_ROLE
        elif path.endswith("/users/roles") and method == "DELETE":
            action = SystemAction.REVOKE_ROLE
        elif path.endswith("/reports") and method == "GET":
            action = SystemAction.VIEW_REPORT
        elif path.endswith("/leave/approve") and method == "POST":
            action = SystemAction.APPROVE_LEAVE
        elif path.endswith("/leave/reject") and method == "POST":
            action = SystemAction.REJECT_LEAVE
        elif path.endswith("/departments") and method == "POST":
            action = SystemAction.CREATE_DEPARTMENT
        elif path.endswith("/departments") and method == "DELETE":
            action = SystemAction.DELETE_DEPARTMENT
        elif method in ["POST", "PUT", "DELETE"]:
            action = SystemAction[method]  # Maps POST->INSERT, PUT->UPDATE, DELETE->DELETE

        if action:
            # Get user_id from request state if available
            user = getattr(request.state, "user", None)
            user_id = user.user_id if user else None
            
            # Log to system_logs table
            async with AsyncSessionLocal() as session:
                try:
                    system_log = SystemLogs(
                        user_id=user_id,
                        action=action,
                        table_affected=path.split("/")[-2] if len(path.split("/")) > 2 else None,
                        record_id=None,  # Could be extracted from path for specific endpoints
                        old_values=None,
                        new_values=None,
                        ip_address=str(request.client.host),
                        user_agent=request.headers.get("user-agent")
                    )
                    session.add(system_log)
                    await session.commit()
                    logger.info(f"Logged system action: {action} for user_id: {user_id}")
                except Exception as e:
                    logger.error(f"Failed to log system action: {str(e)}")
                    await session.rollback()

        return response