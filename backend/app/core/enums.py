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
    TOKEN_REFRESH = "token_refresh"

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

class Permission(str, Enum):
    # Employee permissions
    CLOCK_IN = "clock_in"
    CLOCK_OUT = "clock_out"
    REQUEST_LEAVE = "request_leave"
    VIEW_LEAVE_BALANCE = "view_leave_balance"
    VIEW_OWN_ATTENDANCE = "view_own_attendance"
    CREATE_LEAVE_REQUEST = "create_leave_request"
    VIEW_LEAVE_REQUEST = "view_leave_request"  # MISSING - Added
    UPDATE_LEAVE_REQUEST = "update_leave_request"  # MISSING - Added
    DELETE_LEAVE_REQUEST = "delete_leave_request"  # MISSING - Added
    CREATE_TIME_CORRECTION = "create_time_correction"
    VIEW_TIME_CORRECTION = "view_time_correction"
    UPDATE_TIME_CORRECTION = "update_time_correction"
    DELETE_TIME_CORRECTION = "delete_time_correction"
    REFRESH_TOKEN = "refresh_token"
    VIEW_HOLIDAY = "view_holiday"
    VIEW_OWN_PROFILE = "view_own_profile"  # MISSING - Added
    UPDATE_OWN_PROFILE = "update_own_profile"  # MISSING - Added
    
    # Manager permissions
    APPROVE_LEAVE = "approve_leave"
    REJECT_LEAVE = "reject_leave"  # MISSING - Added
    MANAGE_OVERTIME = "manage_overtime"
    GENERATE_REPORTS = "generate_reports"
    VIEW_TEAM_ATTENDANCE = "view_team_attendance"
    VIEW_LEAVE_APPROVAL = "view_leave_approval"
    VIEW_TEAM_LEAVE_REQUESTS = "view_team_leave_requests"  # MISSING - Added
    CREATE_OVERTIME_RECORD = "create_overtime_record"
    VIEW_OVERTIME_RECORD = "view_overtime_record"
    VIEW_TEAM_OVERTIME_RECORDS = "view_team_overtime_records"
    UPDATE_OVERTIME_RECORD = "update_overtime_record"  # MISSING - Added
    DELETE_OVERTIME_RECORD = "delete_overtime_record"  # MISSING - Added
    VIEW_TEAM_PROFILES = "view_team_profiles"  # MISSING - Added
    
    # HR permissions
    MANAGE_EMPLOYEES = "manage_employees"
    CREATE_USER = "create_user"
    VIEW_USER = "view_user"
    UPDATE_USER = "update_user"
    DELETE_USER = "delete_user"
    VIEW_ALL_ATTENDANCE = "view_all_attendance"
    VIEW_ALL_LEAVE_REQUESTS = "view_all_leave_requests"  # MISSING - Added
    MANAGE_LEAVE_POLICIES = "manage_leave_policies"
    GENERATE_COMPLIANCE_REPORTS = "generate_compliance_reports"
    UPDATE_LEAVE_BALANCE = "update_leave_balance"
    CREATE_LEAVE_POLICY = "create_leave_policy"
    VIEW_LEAVE_POLICY = "view_leave_policy"
    UPDATE_LEAVE_POLICY = "update_leave_policy"
    DELETE_LEAVE_POLICY = "delete_leave_policy"
    CREATE_HOLIDAY = "create_holiday"
    UPDATE_HOLIDAY = "update_holiday"
    DELETE_HOLIDAY = "delete_holiday"
    CREATE_SHIFT_PATTERN = "create_shift_pattern"
    VIEW_SHIFT_PATTERN = "view_shift_pattern"
    UPDATE_SHIFT_PATTERN = "update_shift_pattern"
    DELETE_SHIFT_PATTERN = "delete_shift_pattern"
    VIEW_ALL_OVERTIME_RECORDS = "view_all_overtime_records"  # MISSING - Added
    
    # Admin permissions
    VIEW_LOGS = "view_logs"
    MANAGE_ROLES = "manage_roles"
    CREATE_USER_ROLE = "create_user_role"
    VIEW_USER_ROLE = "view_user_role"
    UPDATE_USER_ROLE = "update_user_role"
    DELETE_USER_ROLE = "delete_user_role"
    MANAGE_USERS = "manage_users"
    MANAGE_DEPARTMENTS = "manage_departments"
    CREATE_DEPARTMENT = "create_department"  # MISSING - Added
    VIEW_DEPARTMENT = "view_department"  # MISSING - Added
    UPDATE_DEPARTMENT = "update_department"  # MISSING - Added
    DELETE_DEPARTMENT = "delete_department"  # MISSING - Added
    CREATE_USER_DEPARTMENT = "create_user_department"
    VIEW_USER_DEPARTMENT = "view_user_department"
    UPDATE_USER_DEPARTMENT = "update_user_department"
    DELETE_USER_DEPARTMENT = "delete_user_department"
    SYSTEM_CONFIGURATION = "system_configuration"
    CREATE_ROLE = "create_role"
    VIEW_ROLE = "view_role"
    UPDATE_ROLE = "update_role"
    DELETE_ROLE = "delete_role"
    CREATE_LOGS = "create_logs"
    
    # Super Admin permissions
    ALL_PERMISSIONS = "all_permissions"

class PermissionGroup(str, Enum):
    """Permission groups for easier management"""
    EMPLOYEE = "employee"
    MANAGER = "manager"
    HR = "hr"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"

# Define permissions hierarchically to avoid circular reference
_EMPLOYEE_PERMISSIONS = [
    Permission.CLOCK_IN,
    Permission.CLOCK_OUT,
    Permission.REQUEST_LEAVE,
    Permission.VIEW_LEAVE_BALANCE,
    Permission.VIEW_OWN_ATTENDANCE,
    Permission.CREATE_LEAVE_REQUEST,
    Permission.VIEW_LEAVE_REQUEST,
    Permission.UPDATE_LEAVE_REQUEST,
    Permission.DELETE_LEAVE_REQUEST,
    Permission.CREATE_TIME_CORRECTION,
    Permission.VIEW_TIME_CORRECTION,
    Permission.REFRESH_TOKEN,
    Permission.VIEW_HOLIDAY,
    Permission.VIEW_OWN_PROFILE,
    Permission.UPDATE_OWN_PROFILE,
]

_MANAGER_PERMISSIONS = [
    Permission.APPROVE_LEAVE,
    Permission.REJECT_LEAVE,
    Permission.MANAGE_OVERTIME,
    Permission.GENERATE_REPORTS,
    Permission.VIEW_TEAM_ATTENDANCE,
    Permission.VIEW_LEAVE_APPROVAL,
    Permission.VIEW_TEAM_LEAVE_REQUESTS,
    Permission.CREATE_OVERTIME_RECORD,
    Permission.VIEW_OVERTIME_RECORD,
    Permission.VIEW_TEAM_OVERTIME_RECORDS,
    Permission.UPDATE_OVERTIME_RECORD,
    Permission.DELETE_OVERTIME_RECORD,
    Permission.VIEW_TEAM_PROFILES,
    Permission.UPDATE_TIME_CORRECTION,
]

_HR_PERMISSIONS = [
    Permission.MANAGE_EMPLOYEES,
    Permission.CREATE_USER,
    Permission.VIEW_USER,
    Permission.UPDATE_USER,
    Permission.DELETE_USER,
    Permission.VIEW_ALL_ATTENDANCE,
    Permission.VIEW_ALL_LEAVE_REQUESTS,
    Permission.MANAGE_LEAVE_POLICIES,
    Permission.GENERATE_COMPLIANCE_REPORTS,
    Permission.UPDATE_LEAVE_BALANCE,
    Permission.CREATE_LEAVE_POLICY,
    Permission.VIEW_LEAVE_POLICY,
    Permission.UPDATE_LEAVE_POLICY,
    Permission.DELETE_LEAVE_POLICY,
    Permission.CREATE_HOLIDAY,
    Permission.UPDATE_HOLIDAY,
    Permission.DELETE_HOLIDAY,
    Permission.CREATE_SHIFT_PATTERN,
    Permission.VIEW_SHIFT_PATTERN,
    Permission.UPDATE_SHIFT_PATTERN,
    Permission.DELETE_SHIFT_PATTERN,
    Permission.VIEW_ALL_OVERTIME_RECORDS,
]

_ADMIN_PERMISSIONS = [
    Permission.VIEW_LOGS,
    Permission.MANAGE_ROLES,
    Permission.CREATE_USER_ROLE,
    Permission.VIEW_USER_ROLE,
    Permission.UPDATE_USER_ROLE,
    Permission.DELETE_USER_ROLE,
    Permission.MANAGE_USERS,
    Permission.MANAGE_DEPARTMENTS,
    Permission.CREATE_DEPARTMENT,
    Permission.VIEW_DEPARTMENT,
    Permission.UPDATE_DEPARTMENT,
    Permission.DELETE_DEPARTMENT,
    Permission.CREATE_USER_DEPARTMENT,
    Permission.VIEW_USER_DEPARTMENT,
    Permission.UPDATE_USER_DEPARTMENT,
    Permission.DELETE_USER_DEPARTMENT,
    Permission.SYSTEM_CONFIGURATION,
    Permission.CREATE_ROLE,
    Permission.VIEW_ROLE,
    Permission.UPDATE_ROLE,
    Permission.DELETE_ROLE,
    Permission.CREATE_LOGS,
    Permission.DELETE_TIME_CORRECTION,
]

# Permission mappings with proper inheritance
PERMISSION_GROUPS = {
    PermissionGroup.EMPLOYEE: _EMPLOYEE_PERMISSIONS,
    
    PermissionGroup.MANAGER: [
        *_EMPLOYEE_PERMISSIONS,
        *_MANAGER_PERMISSIONS,
    ],
    
    PermissionGroup.HR: [
        *_EMPLOYEE_PERMISSIONS,
        *_MANAGER_PERMISSIONS,
        *_HR_PERMISSIONS,
    ],
    
    PermissionGroup.ADMIN: [
        *_EMPLOYEE_PERMISSIONS,
        *_MANAGER_PERMISSIONS,
        *_HR_PERMISSIONS,
        *_ADMIN_PERMISSIONS,
    ],
    
    PermissionGroup.SUPER_ADMIN: [
        # Super Admin has ALL permissions via wildcard
        Permission.ALL_PERMISSIONS,
    ],
}