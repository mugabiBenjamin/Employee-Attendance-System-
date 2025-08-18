from fastapi import FastAPI, Request
from app.core.database import AsyncSessionLocal, startup
from app.core.enums import SystemAction
from app.models.system_logs import SystemLogs
import logging
import uuid

logger = logging.getLogger(__name__)

# Action mapping: (path_suffix, method) -> SystemAction
ACTION_MAPPING = {
    ("/auth/token", "POST"): SystemAction.LOGIN,
    ("/auth/logout", "POST"): SystemAction.LOGOUT,
    ("/attendance/clock_in", "POST"): SystemAction.CLOCK_IN,
    ("/attendance/clock_out", "POST"): SystemAction.CLOCK_OUT,
    ("/users/password", "PUT"): SystemAction.PASSWORD_CHANGE,
    ("/users/me", "PUT"): SystemAction.PROFILE_UPDATE,
    ("/users/export", "GET"): SystemAction.DATA_EXPORT,
    ("/users/import", "POST"): SystemAction.DATA_IMPORT,
    ("/users/roles", "POST"): SystemAction.ASSIGN_ROLE,
    ("/users/roles", "DELETE"): SystemAction.REVOKE_ROLE,
    ("/reports", "GET"): SystemAction.VIEW_REPORT,
    ("/leave/approve", "POST"): SystemAction.APPROVE_LEAVE,
    ("/leave/reject", "POST"): SystemAction.REJECT_LEAVE,
    ("/departments", "POST"): SystemAction.CREATE_DEPARTMENT,
    ("/departments", "DELETE"): SystemAction.DELETE_DEPARTMENT,
}

# Method-based fallback mapping for generic CRUD operations
METHOD_FALLBACK = {
    "POST": SystemAction.INSERT,
    "PUT": SystemAction.UPDATE,
    "DELETE": SystemAction.DELETE,
}

# Route to table mapping for more accurate table_affected derivation
ROUTE_TABLE_MAPPING = {
    "/auth/token": "users",
    "/auth/logout": "users",
    "/attendance/clock_in": "attendance_records",
    "/attendance/clock_out": "attendance_records",
    "/users/password": "users",
    "/users/me": "users",
    "/users/export": "users",
    "/users/import": "users",
    "/users/roles": "user_roles",
    "/reports": "attendance_records",
    "/leave/approve": "leave_requests",
    "/leave/reject": "leave_requests",
    "/departments": "departments",
}

def determine_system_action(path: str, method: str) -> str | None:
    """Determine the system action based on request path and method.
    
    Args:
        path: The request path
        method: The HTTP method
        
    Returns:
        SystemAction value or None if no action should be logged
    """
    # Check for exact path matches first
    for (path_suffix, mapped_method), action in ACTION_MAPPING.items():
        if path.endswith(path_suffix) and method == mapped_method:
            return action
    
    # Fallback to generic method-based actions for POST/PUT/DELETE
    if method in METHOD_FALLBACK:
        return METHOD_FALLBACK[method]
    
    return None

def get_table_affected(path: str) -> str | None:
    """Determine the affected table based on the route path."""
    for route, table in ROUTE_TABLE_MAPPING.items():
        if path.endswith(route):
            return table
    # Fallback to path-based derivation if no exact match
    path_parts = path.split("/")
    return path_parts[-2] if len(path_parts) > 2 else None

def setup_middleware(app: FastAPI) -> None:
    """Setup middleware for logging system actions."""
    # Ensure database is initialized on app startup
    @app.on_event("startup")
    async def app_startup():
        await startup()

    @app.middleware("http")
    async def log_system_actions(request: Request, call_next):
        # Generate unique request_id
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        response = await call_next(request)
        
        # Determine the action based on request method and path
        path = request.url.path
        method = request.method
        action = determine_system_action(path, method)

        if action:
            # Get user_id from request state if available
            user = getattr(request.state, "user", None)
            user_id = user.user_id if user else None
            
            # Safely get client IP
            ip_address = None
            try:
                ip_address = str(request.client.host) if request.client else None
            except Exception as e:
                logger.warning(f"Failed to get client IP: {str(e)}")
            
            # Log to system_logs table
            async with AsyncSessionLocal() as session:
                try:
                    system_log = SystemLogs(
                        user_id=user_id,
                        action=action,
                        table_affected=get_table_affected(path),
                        record_id=None,  # Could be extracted from path for specific endpoints
                        old_values=None,
                        new_values=None,
                        ip_address=ip_address,
                        user_agent=request.headers.get("user-agent"),
                        request_id=request_id
                    )
                    session.add(system_log)
                    await session.commit()
                    logger.info(f"Logged system action: {action} for user_id: {user_id}", extra={"request_id": request_id})
                except Exception as e:
                    logger.error(f"Failed to log system action: {str(e)}", extra={"request_id": request_id})
                    await session.rollback()

        return response