from fastapi import HTTPException, status
from typing import Optional, Dict, Any, Type, List
from enum import Enum

class BaseCustomException(HTTPException):
    """Base class for all custom exceptions with enhanced error handling."""
    def __init__(
        self, 
        detail: str, 
        status_code: int, 
        headers: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.error_code = error_code

class DatabaseError(BaseCustomException):
    """Database operation failures."""
    def __init__(self, detail: str = "Database operation failed", original_error: Optional[Exception] = None):
        super().__init__(
            detail=f"{detail}: {str(original_error)}" if original_error else detail,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="DATABASE_ERROR"
        )
        self.original_error = original_error

class AuthenticationError(BaseCustomException):
    """Authentication failures."""
    def __init__(self, detail: str = "Authentication failed"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
            error_code="AUTH_FAILED"
        )

class AuthorizationError(BaseCustomException):
    """Authorization/permission errors."""
    def __init__(self, detail: str = "Insufficient permissions", missing_permissions: Optional[List[str]] = None):
        if missing_permissions:
            detail = f"{detail}: {', '.join(missing_permissions)}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="PERMISSION_DENIED"
        )

class ValidationError(BaseCustomException):
    """Input validation errors with support for schema-specific rules."""
    def __init__(
        self,
        detail: str = "Invalid input data",
        field: Optional[str] = None,
        enum_type: Optional[Type[Enum]] = None,
        invalid_fields: Optional[Dict[str, str]] = None
    ):
        error_detail = f"{field}: {detail}" if field else detail
        if enum_type:
            error_detail += f". Valid values: {', '.join(enum_type.__members__.keys())}"
        if invalid_fields:
            error_detail += f". Errors: {'; '.join([f'{k}: {v}' for k, v in invalid_fields.items()])}"
        super().__init__(
            detail=error_detail,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR"
        )

class ResourceNotFoundError(BaseCustomException):
    """Generic resource not found error."""
    def __init__(self, resource: str, identifier: Optional[str] = None):
        detail = f"{resource} not found"
        if identifier:
            detail += f": {identifier}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="RESOURCE_NOT_FOUND"
        )

class ResourceConflictError(BaseCustomException):
    """Resource conflict errors (duplicates, constraints)."""
    def __init__(self, detail: str = "Resource conflict", resource_type: Optional[str] = None, conflict_details: Optional[Dict[str, Any]] = None):
        if resource_type:
            detail = f"{resource_type} conflict: {detail}"
        if conflict_details:
            detail += f". Details: {conflict_details}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_409_CONFLICT,
            error_code="RESOURCE_CONFLICT"
        )

class BusinessLogicError(BaseCustomException):
    """Business rule violations."""
    def __init__(self, detail: str = "Business rule violation", rule_name: Optional[str] = None):
        if rule_name:
            detail = f"{detail}: {rule_name}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="BUSINESS_LOGIC_ERROR"
        )

# Resource-specific Not Found Errors
class UserNotFoundError(BaseCustomException):
    """User not found errors."""
    def __init__(self, user_id: Optional[int] = None):
        detail = "User not found"
        if user_id:
            detail += f": ID {user_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="USER_NOT_FOUND"
        )

class DepartmentNotFoundError(BaseCustomException):
    """Department not found errors."""
    def __init__(self, dept_id: Optional[int] = None):
        detail = "Department not found"
        if dept_id:
            detail += f": ID {dept_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="DEPARTMENT_NOT_FOUND"
        )

class RoleNotFoundError(BaseCustomException):
    """Role not found errors."""
    def __init__(self, role_id: Optional[int] = None):
        detail = "Role not found"
        if role_id:
            detail += f": ID {role_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="ROLE_NOT_FOUND"
        )

class UserDepartmentNotFoundError(BaseCustomException):
    """User department assignment not found errors."""
    def __init__(self, user_department_id: Optional[int] = None):
        detail = "User department assignment not found"
        if user_department_id:
            detail += f": ID {user_department_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="USER_DEPARTMENT_NOT_FOUND"
        )

class UserRoleNotFoundError(BaseCustomException):
    """User role assignment not found errors."""
    def __init__(self, user_role_id: Optional[int] = None):
        detail = "User role assignment not found"
        if user_role_id:
            detail += f": ID {user_role_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="USER_ROLE_NOT_FOUND"
        )

class LeavePolicyNotFoundError(BaseCustomException):
    """Leave policy not found errors."""
    def __init__(self, policy_id: Optional[int] = None):
        detail = "Leave policy not found"
        if policy_id:
            detail += f": ID {policy_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="LEAVE_POLICY_NOT_FOUND"
        )

class ShiftAssignmentNotFoundError(BaseCustomException):
    """Shift assignment not found errors."""
    def __init__(self, shift_id: Optional[int] = None):
        detail = "Shift assignment not found"
        if shift_id:
            detail += f": ID {shift_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="SHIFT_ASSIGNMENT_NOT_FOUND"
        )

class ShiftPatternNotFoundError(BaseCustomException):
    """Shift pattern not found errors."""
    def __init__(self, pattern_id: Optional[int] = None):
        detail = "Shift pattern not found"
        if pattern_id:
            detail += f": ID {pattern_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="SHIFT_PATTERN_NOT_FOUND"
        )

class OvertimeRecordNotFoundError(BaseCustomException):
    """Overtime record not found errors."""
    def __init__(self, record_id: Optional[int] = None):
        detail = "Overtime record not found"
        if record_id:
            detail += f": ID {record_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="OVERTIME_RECORD_NOT_FOUND"
        )

class LeaveBalanceNotFoundError(BaseCustomException):
    """Leave balance not found errors."""
    def __init__(self, balance_id: Optional[int] = None):
        detail = "Leave balance not found"
        if balance_id:
            detail += f": ID {balance_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="LEAVE_BALANCE_NOT_FOUND"
        )

class HolidayNotFoundError(BaseCustomException):
    """Holiday not found errors."""
    def __init__(self, holiday_id: Optional[int] = None):
        detail = "Holiday not found"
        if holiday_id:
            detail += f": ID {holiday_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="HOLIDAY_NOT_FOUND"
        )

class LeaveRequestNotFoundError(BaseCustomException):
    """Leave request not found errors."""
    def __init__(self, request_id: Optional[int] = None):
        detail = "Leave request not found"
        if request_id:
            detail += f": ID {request_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="LEAVE_REQUEST_NOT_FOUND"
        )

class TimeCorrectionNotFoundError(BaseCustomException):
    """Time correction not found errors."""
    def __init__(self, correction_id: Optional[int] = None):
        detail = "Time correction not found"
        if correction_id:
            detail += f": ID {correction_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="TIME_CORRECTION_NOT_FOUND"
        )

class EmployeeEmergencyContactNotFoundError(BaseCustomException):
    """Employee emergency contact not found errors."""
    def __init__(self, contact_id: Optional[int] = None):
        detail = "Emergency contact not found"
        if contact_id:
            detail += f": ID {contact_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="EMERGENCY_CONTACT_NOT_FOUND"
        )

class AttendanceRecordNotFoundError(BaseCustomException):
    """Attendance record not found errors."""
    def __init__(self, record_id: Optional[int] = None):
        detail = "Attendance record not found"
        if record_id:
            detail += f": ID {record_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="ATTENDANCE_RECORD_NOT_FOUND"
        )

class EmployeeHierarchyNotFoundError(BaseCustomException):
    """Employee hierarchy not found errors."""
    def __init__(self, hierarchy_id: Optional[int] = None):
        detail = "Employee hierarchy not found"
        if hierarchy_id:
            detail += f": ID {hierarchy_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="EMPLOYEE_HIERARCHY_NOT_FOUND"
        )

class HolidayCalendarNotFoundError(BaseCustomException):
    """Holiday calendar not found errors."""
    def __init__(self, holiday_id: Optional[int] = None):
        detail = "Holiday calendar not found"
        if holiday_id:
            detail += f": ID {holiday_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="HOLIDAY_CALENDAR_NOT_FOUND"
        )

class LeaveApprovalWorkflowNotFoundError(BaseCustomException):
    """Leave approval workflow not found errors."""
    def __init__(self, workflow_id: Optional[int] = None):
        detail = "Leave approval workflow not found"
        if workflow_id:
            detail += f": ID {workflow_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="LEAVE_APPROVAL_WORKFLOW_NOT_FOUND"
        )

class SystemLogNotFoundError(BaseCustomException):
    """System log not found errors."""
    def __init__(self, log_id: Optional[int] = None):
        detail = "System log not found"
        if log_id:
            detail += f": ID {log_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="SYSTEM_LOG_NOT_FOUND"
        )

# Business Logic Errors
class LeavePolicyError(BusinessLogicError):
    """Leave policy specific errors."""
    def __init__(self, detail: str = "Invalid leave policy"):
        super().__init__(detail, "LeavePolicy")
        self.error_code = "LEAVE_POLICY_INVALID"

class OvertimePolicyError(BusinessLogicError):
    """Overtime policy specific errors."""
    def __init__(self, detail: str = "Invalid overtime policy"):
        super().__init__(detail, "OvertimePolicy")
        self.error_code = "OVERTIME_POLICY_INVALID"

class LeaveRequestError(BusinessLogicError):
    """Leave request specific errors."""
    def __init__(self, detail: str = "Invalid leave request"):
        super().__init__(detail, "LeaveRequest")
        self.error_code = "LEAVE_REQUEST_INVALID"

class AttendanceError(BusinessLogicError):
    """Attendance operation errors."""
    def __init__(self, detail: str = "Invalid attendance operation"):
        super().__init__(detail, "Attendance")
        self.error_code = "ATTENDANCE_INVALID"

class AttendanceOperationError(BusinessLogicError):
    """Attendance clock-in or clock-out operation errors."""
    def __init__(self, detail: str = "Attendance operation failed", operation: Optional[str] = None):
        super().__init__(detail, f"AttendanceOperation_{operation}" if operation else "AttendanceOperation")
        self.error_code = f"ATTENDANCE_{operation.upper()}_INVALID" if operation else "ATTENDANCE_OPERATION_INVALID"

class DuplicateAttendanceError(ResourceConflictError):
    """Duplicate attendance record errors."""
    def __init__(self, detail: str = "Duplicate attendance record"):
        super().__init__(detail, "Attendance")
        self.error_code = "ATTENDANCE_DUPLICATE"

class ShiftAssignmentError(BusinessLogicError):
    """Shift assignment specific errors."""
    def __init__(self, detail: str = "Invalid shift assignment"):
        super().__init__(detail, "ShiftAssignment")
        self.error_code = "SHIFT_ASSIGNMENT_INVALID"

class ShiftPatternError(BusinessLogicError):
    """Shift pattern configuration errors."""
    def __init__(self, detail: str = "Invalid shift pattern"):
        super().__init__(detail, "ShiftPattern")
        self.error_code = "SHIFT_PATTERN_INVALID"

class OvertimeRecordError(BusinessLogicError):
    """Overtime record specific errors."""
    def __init__(self, detail: str = "Invalid overtime record"):
        super().__init__(detail, "OvertimeRecord")
        self.error_code = "OVERTIME_RECORD_INVALID"

class LeaveBalanceError(BusinessLogicError):
    """Leave balance specific errors."""
    def __init__(self, detail: str = "Leave balance error"):
        super().__init__(detail, "LeaveBalance")
        self.error_code = "LEAVE_BALANCE_INVALID"

class InsufficientLeaveBalanceError(LeaveBalanceError):
    """Insufficient leave balance errors."""
    def __init__(self, detail: str = "Insufficient leave balance"):
        super().__init__(detail)
        self.error_code = "LEAVE_BALANCE_INSUFFICIENT"

class NegativeBalanceError(LeaveBalanceError):
    """Negative balance errors."""
    def __init__(self, detail: str = "Negative balance not allowed"):
        super().__init__(detail)
        self.error_code = "LEAVE_BALANCE_NEGATIVE"

class EmployeeHierarchyError(BusinessLogicError):
    """Employee hierarchy specific errors (e.g., circular reporting)."""
    def __init__(self, detail: str = "Invalid employee hierarchy"):
        super().__init__(detail, "EmployeeHierarchy")
        self.error_code = "EMPLOYEE_HIERARCHY_INVALID"

class HolidayCalendarError(BusinessLogicError):
    """Holiday calendar specific errors."""
    def __init__(self, detail: str = "Invalid holiday calendar operation"):
        super().__init__(detail, "HolidayCalendar")
        self.error_code = "HOLIDAY_CALENDAR_INVALID"

class LeaveApprovalWorkflowError(BusinessLogicError):
    """Leave approval workflow specific errors."""
    def __init__(self, detail: str = "Invalid leave approval workflow"):
        super().__init__(detail, "LeaveApprovalWorkflow")
        self.error_code = "LEAVE_APPROVAL_WORKFLOW_INVALID"

class TimeCorrectionError(BusinessLogicError):
    """Time correction specific errors."""
    def __init__(self, detail: str = "Invalid time correction request"):
        super().__init__(detail, "TimeCorrection")
        self.error_code = "TIME_CORRECTION_INVALID"

class EmployeeEmergencyContactError(BusinessLogicError):
    """Employee emergency contact specific errors."""
    def __init__(self, detail: str = "Invalid emergency contact operation"):
        super().__init__(detail, "EmployeeEmergencyContact")
        self.error_code = "EMERGENCY_CONTACT_INVALID"

class AttendanceSummaryError(BusinessLogicError):
    """Attendance summary specific errors."""
    def __init__(self, detail: str = "Invalid attendance summary"):
        super().__init__(detail, "AttendanceSummary")
        self.error_code = "ATTENDANCE_SUMMARY_INVALID"
        
class FileUploadError(BaseCustomException):
    """File upload related errors."""
    def __init__(self, detail: str = "File upload error", status_override: Optional[int] = None):
        super().__init__(
            detail=detail,
            status_code=status_override or status.HTTP_400_BAD_REQUEST,
            error_code="FILE_UPLOAD_ERROR"
        )

class WorkflowStateError(BusinessLogicError):
    """Invalid workflow state transitions."""
    def __init__(self, detail: str = "Invalid state transition", from_state: Optional[str] = None, to_state: Optional[str] = None):
        if from_state and to_state:
            detail = f"Cannot transition from {from_state} to {to_state}: {detail}"
        super().__init__(detail, "WorkflowState")
        self.error_code = "WORKFLOW_STATE_INVALID"

# Convenience functions for common cases
def user_not_found(user_id: Optional[int] = None):
    return UserNotFoundError(user_id)

def department_not_found(dept_id: Optional[int] = None):
    return DepartmentNotFoundError(dept_id)

def role_not_found(role_id: Optional[int] = None):
    return RoleNotFoundError(role_id)

def user_department_not_found(user_department_id: Optional[int] = None):
    return UserDepartmentNotFoundError(user_department_id)

def user_role_not_found(user_role_id: Optional[int] = None):
    return UserRoleNotFoundError(user_role_id)

def leave_policy_not_found(policy_id: Optional[int] = None):
    return LeavePolicyNotFoundError(policy_id)

def shift_assignment_not_found(shift_id: Optional[int] = None):
    return ShiftAssignmentNotFoundError(shift_id)

def shift_pattern_not_found(pattern_id: Optional[int] = None):
    return ShiftPatternNotFoundError(pattern_id)

def overtime_record_not_found(record_id: Optional[int] = None):
    return OvertimeRecordNotFoundError(record_id)

def leave_balance_not_found(balance_id: Optional[int] = None):
    return LeaveBalanceNotFoundError(balance_id)

def holiday_not_found(holiday_id: Optional[int] = None):
    return HolidayNotFoundError(holiday_id)

def leave_request_not_found(request_id: Optional[int] = None):
    return LeaveRequestNotFoundError(request_id)

def time_correction_not_found(correction_id: Optional[int] = None):
    return TimeCorrectionNotFoundError(correction_id)

def emergency_contact_not_found(contact_id: Optional[int] = None):
    return EmployeeEmergencyContactNotFoundError(contact_id)

def attendance_record_not_found(record_id: Optional[int] = None):
    return AttendanceRecordNotFoundError(record_id)

def employee_hierarchy_not_found(hierarchy_id: Optional[int] = None):
    return EmployeeHierarchyNotFoundError(hierarchy_id)

def holiday_calendar_not_found(holiday_id: Optional[int] = None):
    return HolidayCalendarNotFoundError(holiday_id)

def leave_approval_workflow_not_found(workflow_id: Optional[int] = None):
    return LeaveApprovalWorkflowNotFoundError(workflow_id)

def system_log_not_found(log_id: Optional[int] = None):
    return SystemLogNotFoundError(log_id)

def insufficient_leave_balance(detail: str = "Insufficient leave balance"):
    return InsufficientLeaveBalanceError(detail)

def negative_balance(detail: str = "Negative balance not allowed"):
    return NegativeBalanceError(detail)

def duplicate_attendance(detail: str = "Duplicate attendance record"):
    return DuplicateAttendanceError(detail)

def attendance_operation_failed(detail: str = "Attendance operation failed", operation: Optional[str] = None):
    return AttendanceOperationError(detail, operation)

def workflow_state_error(detail: str, from_state: Optional[str] = None, to_state: Optional[str] = None):
    return WorkflowStateError(detail, from_state, to_state)