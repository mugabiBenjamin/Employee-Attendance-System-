from fastapi import APIRouter

from app.api.v1.endpoints import (
    attendance_records,
    auth,
    departments,
    employee_emergency_contacts,
    employee_hierarchy,
    leave_requests,
    roles,
    shift_assignments,
    shift_patterns,
    system_logs,
    user_departments,
    user_roles,
    users,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
api_router.include_router(user_roles.router)
api_router.include_router(departments.router)
api_router.include_router(user_departments.router)
api_router.include_router(attendance_records.router)
api_router.include_router(leave_requests.router)
api_router.include_router(employee_emergency_contacts.router)
api_router.include_router(employee_hierarchy.router)
api_router.include_router(shift_patterns.router)
api_router.include_router(shift_assignments.router)
api_router.include_router(system_logs.router)