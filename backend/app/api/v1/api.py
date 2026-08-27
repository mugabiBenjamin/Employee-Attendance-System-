from fastapi import APIRouter

# Import routers safely encapsulated by the endpoints package
from app.api.v1.endpoints import (
    auth_router,
    users_router,
    roles_router,
    user_roles_router,
    departments_router,
    user_departments_router,
    attendance_records_router,
    attendance_summary_router,
    leave_requests_router,
    leave_balances_router,
    leave_policies_router,
    workflows_router,
    emergency_contacts_router,
    hierarchy_router,
    shift_patterns_router,
    shift_assignments_router,
    holidays_router,
    overtime_router,
    time_corrections_router,
    system_logs_router,
    enums_router,
)

api_router = APIRouter()

# Authentication & Authorization
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(roles_router)
api_router.include_router(user_roles_router)

# Organization
api_router.include_router(departments_router)
api_router.include_router(user_departments_router)
api_router.include_router(hierarchy_router)
api_router.include_router(emergency_contacts_router)

# Time & Attendance
api_router.include_router(attendance_records_router)
api_router.include_router(attendance_summary_router)
api_router.include_router(time_corrections_router)
api_router.include_router(overtime_router)
api_router.include_router(holidays_router)

# Leave Management
api_router.include_router(leave_requests_router)
api_router.include_router(leave_balances_router)
api_router.include_router(leave_policies_router)
api_router.include_router(workflows_router)

# Shift Management
api_router.include_router(shift_patterns_router)
api_router.include_router(shift_assignments_router)

# System Admin
api_router.include_router(system_logs_router)
api_router.include_router(enums_router)