from enum import Enum

class SystemAction(str, Enum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    CLOCK_IN = "CLOCK_IN"
    CLOCK_OUT = "CLOCK_OUT"
    password_change = "password_change"
    profile_update = "profile_update"
    data_export = "data_export"
    data_import = "data_import"
    assign_role = "assign_role"
    revoke_role = "revoke_role"
    view_report = "view_report"
    approve_leave = "approve_leave"
    reject_leave = "reject_leave"
    create_department = "create_department"
    delete_department = "delete_department"

class AttendanceStatus(str, Enum):
    present = "present"
    absent = "absent"
    late = "late"
    early_departure = "early_departure"
    on_leave = "on_leave"
    half_day = "half_day"
    sick = "sick"

class LeaveRequestStatus(str, Enum):
    draft = "draft"
    under_review = "under_review"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"
    completed = "completed"

class LeaveType(str, Enum):
    annual = "annual"
    sick = "sick"
    maternity = "maternity"
    paternity = "paternity"
    emergency = "emergency"
    unpaid = "unpaid"
    casual = "casual"
    compensatory = "compensatory"
    bereavement = "bereavement"
    leave_of_absence = "leave_of_absence"
    public_holiday = "public_holiday"

class CorrectionStatus(str, Enum):
    draft = "draft"
    under_review = "under_review"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"
    completed = "completed"

class EmployeeType(str, Enum):
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"
    intern = "intern"
    temporary = "temporary"

class ShiftType(str, Enum):
    morning = "morning"
    afternoon = "afternoon"
    night = "night"
    flexible = "flexible"
    split = "split"