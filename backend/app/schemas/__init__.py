from app.schemas.auth_schema import Token, LoginCredentials, UserProfile, RefreshTokenRequest
from app.schemas.user import UserCreate, UserUpdate, UserOut
from app.schemas.department import DepartmentCreate, DepartmentUpdate, DepartmentOut
from app.schemas.role import RoleCreate, RoleUpdate, RoleOut
from app.schemas.attendance_record import AttendanceRecordCreate, AttendanceRecordUpdate, AttendanceRecordOut, ClockInOut
from app.schemas.leave_request import LeaveRequestCreate, LeaveRequestUpdate, LeaveRequestOut, LeaveApprovalUpdate

# Add other schemas as needed for direct top-level import

__all__ = [
    "Token",
    "LoginCredentials",
    "UserProfile",
    "RefreshTokenRequest",
    "UserCreate",
    "UserUpdate",
    "UserOut",
    "DepartmentCreate",
    "DepartmentUpdate",
    "DepartmentOut",
    "RoleCreate",
    "RoleUpdate",
    "RoleOut",
    "AttendanceRecordCreate",
    "AttendanceRecordUpdate",
    "AttendanceRecordOut",
    "ClockInOut",
    "LeaveRequestCreate",
    "LeaveRequestUpdate",
    "LeaveRequestOut",
    "LeaveApprovalUpdate"
]