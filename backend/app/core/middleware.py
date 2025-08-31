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
    async def log_system_actions(request: Request, call_next, db: AsyncSession = Depends(get_db)):
        print(f"Request query params: {dict(request.query_params)}")
        print(f"Request path params: {request.path_params}")
        
        request_id = str(uuid.uuid4())
        # Ensure logger is callable
        log_func = logger.info if callable(getattr(logger, 'info', None)) else print
        log_func(f"Middleware processing: {request.method} {request.url.path}", extra={"request_id": request_id} if log_func == logger.info else None)
        
        # Safe way to set request_id on request state
        if not hasattr(request, 'state'):
            request.state = type('State', (), {})()
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        except Exception as e:
            error_msg = f"Error during call_next: {str(e)}"
            if callable(getattr(logger, 'error', None)):
                logger.error(error_msg, extra={"request_id": request_id})
            else:
                print(f"Warning: {error_msg}")
            raise

        path = request.url.path
        method = request.method

        # Skip logging for /api/v1/auth/token to prevent duplicate SystemLogs entries
        if path.endswith(f"{settings.API_V1_STR}/auth/token"):
            debug_func = logger.debug if callable(getattr(logger, 'debug', None)) else print
            debug_func(f"Skipping system log for endpoint: {path}", extra={"request_id": request_id} if debug_func == logger.debug else None)
            return response

        action = determine_system_action(path, method)

        if action:
            # Safe way to get user from request state
            user = getattr(request.state, "user", None)
            user_id = getattr(user, 'user_id', None) if user else None

            ip_address = None
            try:
                ip_address = str(request.client.host) if request.client else None
            except Exception as e:
                warn_func = logger.warning if callable(getattr(logger, 'warning', None)) else print
                warn_func(f"Failed to get client IP: {str(e)}", extra={"request_id": request_id} if warn_func == logger.warning else None)

            async def log_action(session: AsyncSession):
                try:
                    system_log = SystemLogs(
                        user_id=user_id,
                        action=action,
                        table_affected=get_table_affected(path),
                        record_id=None,
                        old_values=None,
                        new_values=None,
                        ip_address=ip_address,
                        user_agent=request.headers.get("user-agent"),
                        request_id=request_id
                    )
                    session.add(system_log)
                    await session.commit()
                    info_func = logger.info if callable(getattr(logger, 'info', None)) else print
                    info_func(
                        f"Logged system action: {action} for user_id: {user_id}",
                        extra={"request_id": request_id} if info_func == logger.info else None
                    )
                except Exception as e:
                    error_func = logger.error if callable(getattr(logger, 'error', None)) else print
                    error_func(
                        f"Failed to log system action: {str(e)}",
                        extra={"request_id": request_id} if error_func == logger.error else None
                    )
                    await session.rollback()

            try:
                # Ensure db is an AsyncSession instance, create new session if not
                session = db if isinstance(db, AsyncSession) else AsyncSessionLocal()
                try:
                    await log_action(session)
                finally:
                    # Close the session only if we created a new one
                    if not isinstance(db, AsyncSession):
                        await session.close()
            except Exception as e:
                error_func = logger.error if callable(getattr(logger, 'error', None)) else print
                error_func(f"Unexpected error in middleware logging: {str(e)}", extra={"request_id": request_id} if error_func == logger.error else None)

        return response