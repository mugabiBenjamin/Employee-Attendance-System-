from app.api.v1.endpoints.attendance_records import router as attendance_records_router
from app.api.v1.endpoints.attendance_summary import router as attendance_summary_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.departments import router as departments_router
from app.api.v1.endpoints.employee_emergency_contacts import router as emergency_contacts_router
from app.api.v1.endpoints.employee_hierarchy import router as hierarchy_router
from app.api.v1.endpoints.enums import router as enums_router
from app.api.v1.endpoints.holiday_calendar import router as holidays_router
from app.api.v1.endpoints.leave_approval_workflow import router as workflows_router
from app.api.v1.endpoints.leave_balances import router as leave_balances_router
from app.api.v1.endpoints.leave_policies import router as leave_policies_router
from app.api.v1.endpoints.leave_requests import router as leave_requests_router
from app.api.v1.endpoints.overtime_records import router as overtime_router
from app.api.v1.endpoints.roles import router as roles_router
from app.api.v1.endpoints.shift_assignments import router as shift_assignments_router
from app.api.v1.endpoints.shift_patterns import router as shift_patterns_router
from app.api.v1.endpoints.system_logs import router as system_logs_router
from app.api.v1.endpoints.time_corrections import router as time_corrections_router
from app.api.v1.endpoints.user_departments import router as user_departments_router
from app.api.v1.endpoints.user_roles import router as user_roles_router
from app.api.v1.endpoints.users import router as users_router

__all__ = [
    "attendance_records_router",
    "attendance_summary_router",
    "auth_router",
    "departments_router",
    "emergency_contacts_router",
    "hierarchy_router",
    "enums_router",
    "holidays_router",
    "workflows_router",
    "leave_balances_router",
    "leave_policies_router",
    "leave_requests_router",
    "overtime_router",
    "roles_router",
    "shift_assignments_router",
    "shift_patterns_router",
    "system_logs_router",
    "time_corrections_router",
    "user_departments_router",
    "user_roles_router",
    "users_router",
]