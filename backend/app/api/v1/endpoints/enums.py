from fastapi import APIRouter
from app.core import enums

router = APIRouter(prefix="/enums", tags=["enums"])

@router.get("/attendance-status")
def get_attendance_status():
    return [status.value for status in enums.AttendanceStatus]

@router.get("/leave-request-status")
def get_leave_request_status():
    return [status.value for status in enums.LeaveRequestStatus]

@router.get("/leave-types")
def get_leave_types():
    return [leave.value for leave in enums.LeaveType]

@router.get("/employee-types")
def get_employee_types():
    return [etype.value for etype in enums.EmployeeType]

@router.get("/permissions")
def get_permissions():
    return enums.get_all_permission_values()

@router.get("/permission-groups")
def get_permission_groups():
    return {
        group.value: [p.value for p in permissions]
        for group, permissions in enums.PERMISSION_GROUPS.items()
    }
