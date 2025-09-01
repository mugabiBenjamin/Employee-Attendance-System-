from fastapi import FastAPI, Request, Depends
from app.core.database import get_db, AsyncSessionLocal
from app.core.enums import SystemAction
from app.models.system_logs import SystemLogs
from app.core.config import settings
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import uuid
import re

logger = logging.getLogger(__name__)

def determine_system_action(path: str, method: str) -> str | None:
    """Determine the system action based on request path and method."""
    path = re.sub(f"^{settings.API_V1_STR}", "", path)

    for (path_suffix, mapped_method), action in settings.ACTION_MAPPING.items():
        if path.endswith(path_suffix) and method == mapped_method:
            return action

    METHOD_FALLBACK = {
        "POST": SystemAction.INSERT.value,
        "PUT": SystemAction.UPDATE.value,
        "DELETE": SystemAction.DELETE.value,
    }
    return METHOD_FALLBACK.get(method)

def get_table_affected(path: str) -> str | None:
    """Determine the affected table based on the route path."""
    path = re.sub(f"^{settings.API_V1_STR}", "", path)

    for route, table in settings.ROUTE_TABLE_MAPPING.items():
        if path.endswith(route):
            return table

    path_parts = path.strip("/").split("/")
    if len(path_parts) >= 2:
        potential_table = path_parts[-2]
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

    @app.middleware("http")
    async def log_system_actions(request: Request, call_next):
        print(f"Request query params: {dict(request.query_params)}")
        print(f"Request path params: {request.path_params}")
        
        request_id = str(uuid.uuid4())
        logger.info(f"Middleware processing: {request.method} {request.url.path}", extra={"request_id": request_id})
        
        # Safe way to set request_id on request state
        if not hasattr(request, 'state'):
            request.state = type('State', (), {})()
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        except Exception as e:
            logger.error(f"Error during call_next: {str(e)}", extra={"request_id": request_id})
            raise

        # REMOVED DATABASE LOGGING TO FIX GREENLET ERROR
        # The SystemLogs creation should be handled in individual service methods, not middleware
        logger.info(f"Request completed: {request.method} {request.url.path}", extra={"request_id": request_id})
        
        return response