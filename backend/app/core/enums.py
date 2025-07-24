from enum import Enum

class SystemAction(str, Enum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    CLOCK_IN = "CLOCK_IN"
    CLOCK_OUT = "CLOCK_OUT"
    PASSWORD_CHANGE = "password_change"
    PROFILE_UPDATE = "profile_update"
    DATA_EXPORT = "data_export"
    DATA_IMPORT = "data_import"
    ASSIGN_ROLE = "assign_role"
    REVOKE_ROLE = "revoke_role"
    VIEW_REPORT = "view_report"
    APPROVE_LEAVE = "approve_leave"
    REJECT_LEAVE = "reject_leave"
    CREATE_DEPARTMENT = "create_department"
    DELETE_DEPARTMENT = "delete_department"

class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    EARLY_DEPARTURE = "early_departure"
    ON_LEAVE = "on_leave"
    HALF_DAY = "half_day"
    SICK = "sick"

class LeaveRequestStatus(str, Enum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    COMPLETED = "completed"

class LeaveType(str, Enum):
    ANNUAL = "annual"
    SICK = "sick"
    MATERNITY = "maternity"
    PATERNITY = "paternity"
    EMERGENCY = "emergency"
    UNPAID = "unpaid"
    CASUAL = "casual"
    COMPENSATORY = "compensatory"
    BEREAVEMENT = "bereavement"
    LEAVE_OF_ABSENCE = "leave_of_absence"
    PUBLIC_HOLIDAY = "public_holiday"

class CorrectionStatus(str, Enum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    COMPLETED = "completed"

class EmployeeType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERN = "intern"
    TEMPORARY = "temporary"

class ShiftType(str, Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    NIGHT = "night"
    FLEXIBLE = "flexible"
    SPLIT = "split"