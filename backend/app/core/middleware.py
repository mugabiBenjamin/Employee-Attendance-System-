from fastapi import FastAPI, Request
from app.core.database import AsyncSessionLocal, startup
from app.core.enums import SystemAction
from app.models.system_logs import SystemLogs
from app.core.config import settings
import logging
import uuid
import re

logger = logging.getLogger(__name__)

def determine_system_action(path: str, method: str) -> str | None:
    """Determine the system action based on request path and method.
    
    Args:
        path: The request path
        method: The HTTP method
        
    Returns:
        SystemAction value or None if no action should be logged
    """
    # Strip API version prefix for matching
    path = re.sub(f"^{settings.API_V1_STR}", "", path)
    
    # Check for exact path matches first
    for (path_suffix, mapped_method), action in settings.ACTION_MAPPING.items():
        if path.endswith(path_suffix) and method == mapped_method:
            return action
    
    # Fallback to generic method-based actions for POST/PUT/DELETE
    METHOD_FALLBACK = {
        "POST": SystemAction.INSERT.value,
        "PUT": SystemAction.UPDATE.value,
        "DELETE": SystemAction.DELETE.value,
    }
    if method in METHOD_FALLBACK:
        return METHOD_FALLBACK[method]
    
    return None

def get_table_affected(path: str) -> str | None:
    """Determine the affected table based on the route path."""
    # Strip API version prefix for matching
    path = re.sub(f"^{settings.API_V1_STR}", "", path)
    
    # Check for exact match in ROUTE_TABLE_MAPPING
    for route, table in settings.ROUTE_TABLE_MAPPING.items():
        if path.endswith(route):
            return table
    
    # Fallback: Derive table name from the second-to-last path segment
    # e.g., /api/v1/users/123 -> "users"
    path_parts = path.strip("/").split("/")
    if len(path_parts) >= 2:
        # Handle cases like "leave_requests/approve" by taking the main resource
        potential_table = path_parts[-2]
        # Map to known table names if possible
        table_name_map = {
            "users": "users",
            "attendance": "attendance_records",
            "leave": "leave_requests",
            "leave_requests": "leave_requests",
            "departments": "departments",
            "holidays": "holiday_calendar",
            "overtime": "overtime_records",
            "roles": "roles",
            "emergency_contacts": "employee_emergency_contacts",
            "hierarchy": "employee_hierarchy",
            "workflows": "leave_approval_workflow",
            "leave_balances": "leave_balances",
            "leave_policies": "leave_policies",
            "shift_patterns": "shift_patterns",
            "shift_assignments": "shift_assignments",
            "user_roles": "user_roles",
            "user_departments": "user_departments",
            "time_corrections": "time_corrections",
        }
        return table_name_map.get(potential_table, potential_table)
    
    return None

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