from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
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
    """Input validation errors."""
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

class EmailSendingError(BaseCustomException):
    """Email sending failures."""
    def __init__(self, detail: str = "Failed to send email", original_error: Optional[Exception] = None):
        super().__init__(
            detail=f"{detail}: {str(original_error)}" if original_error else detail,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="EMAIL_SENDING_ERROR"
        )

class CacheError(BaseCustomException):
    """Cache operation failures."""
    def __init__(self, detail: str = "Cache operation failed", original_error: Optional[Exception] = None):
        super().__init__(
            detail=f"{detail}: {str(original_error)}" if original_error else detail,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="CACHE_ERROR"
        )

class LoggingError(BaseCustomException):
    """Logging operation failures."""
    def __init__(self, detail: str = "Logging operation failed", original_error: Optional[Exception] = None):
        super().__init__(
            detail=f"{detail}: {str(original_error)}" if original_error else detail,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="LOGGING_ERROR"
        )

class RequestIdError(BaseCustomException):
    """Request ID validation errors."""
    def __init__(self, detail: str = "Invalid or missing request ID"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="REQUEST_ID_ERROR"
        )

class CeleryTaskError(BaseCustomException):
    """Celery task execution failures."""
    def __init__(self, detail: str = "Celery task failed", task_id: Optional[str] = None, original_error: Optional[Exception] = None):
        error_detail = f"{detail}: task_id={task_id}" if task_id else detail
        if original_error:
            error_detail += f": {str(original_error)}"
        super().__init__(
            detail=error_detail,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="CELERY_TASK_ERROR"
        )

class RedisError(BaseCustomException):
    """Redis operation failures."""
    def __init__(self, detail: str = "Redis operation failed", original_error: Optional[Exception] = None):
        super().__init__(
            detail=f"{detail}: {str(original_error)}" if original_error else detail,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="REDIS_ERROR"
        )

class LeavePolicyError(BusinessLogicError):
    """Leave policy specific errors."""
    def __init__(self, detail: str = "Invalid leave policy"):
        super().__init__(detail)
        self.error_code = "LEAVE_POLICY_ERROR"

class OvertimePolicyError(BusinessLogicError):
    """Overtime policy specific errors."""
    def __init__(self, detail: str = "Invalid overtime policy"):
        super().__init__(detail)
        self.error_code = "OVERTIME_POLICY_ERROR"

class RateLimitError(BaseCustomException):
    """Rate limit exceeded errors."""
    def __init__(self, detail: str = "Too many requests"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="RATE_LIMIT_ERROR"
        )

class SessionError(BaseCustomException):
    """Session management errors."""
    def __init__(self, detail: str = "Invalid or expired session"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
            error_code="SESSION_ERROR"
        )

# Specific domain exceptions
class UserNotFoundError(BaseCustomException):
    """User not found errors."""
    def __init__(self, user_id: Optional[int] = None):
        detail = f"User not found"
        if user_id:
            detail += f": ID {user_id}"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="USER_NOT_FOUND"
        )

class LeaveRequestError(BusinessLogicError):
    """Leave request specific errors."""
    def __init__(self, detail: str = "Invalid leave request"):
        super().__init__(detail)
        self.error_code = "LEAVE_REQUEST_ERROR"

class AttendanceError(BusinessLogicError):
    """Attendance operation errors."""
    def __init__(self, detail: str = "Invalid attendance operation"):
        super().__init__(detail)
        self.error_code = "ATTENDANCE_ERROR"

class FileUploadError(BaseCustomException):
    """File upload errors."""
    def __init__(self, detail: str = "File upload failed"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="FILE_UPLOAD_ERROR"
        )

class ShiftAssignmentError(BusinessLogicError):
    """Shift assignment specific errors."""
    def __init__(self, detail: str = "Invalid shift assignment"):
        super().__init__(detail)
        self.error_code = "SHIFT_ASSIGNMENT_ERROR"

class ShiftPatternError(BusinessLogicError):
    """Shift pattern configuration errors."""
    def __init__(self, detail: str = "Invalid shift pattern"):
        super().__init__(detail)
        self.error_code = "SHIFT_PATTERN_ERROR"

class OvertimeRecordError(BusinessLogicError):
    """Overtime record specific errors."""
    def __init__(self, detail: str = "Invalid overtime record"):
        super().__init__(detail)
        self.error_code = "OVERTIME_RECORD_ERROR"

class LeaveBalanceError(BusinessLogicError):
    """Leave balance specific errors (e.g., insufficient balance)."""
    def __init__(self, detail: str = "Insufficient leave balance"):
        super().__init__(detail)
        self.error_code = "LEAVE_BALANCE_ERROR"

class EmployeeHierarchyError(BusinessLogicError):
    """Employee hierarchy specific errors (e.g., circular reporting)."""
    def __init__(self, detail: str = "Invalid employee hierarchy"):
        super().__init__(detail)
        self.error_code = "EMPLOYEE_HIERARCHY_ERROR"

class HolidayCalendarError(BusinessLogicError):
    """Holiday calendar specific errors."""
    def __init__(self, detail: str = "Invalid holiday calendar operation"):
        super().__init__(detail)
        self.error_code = "HOLIDAY_CALENDAR_ERROR"

class LeaveApprovalWorkflowError(BusinessLogicError):
    """Leave approval workflow specific errors."""
    def __init__(self, detail: str = "Invalid leave approval workflow"):
        super().__init__(detail)
        self.error_code = "LEAVE_APPROVAL_WORKFLOW_ERROR"

class TimeCorrectionError(BusinessLogicError):
    """Time correction specific errors."""
    def __init__(self, detail: str = "Invalid time correction request"):
        super().__init__(detail)
        self.error_code = "TIME_CORRECTION_ERROR"

class EmployeeEmergencyContactError(BusinessLogicError):
    """Employee emergency contact specific errors."""
    def __init__(self, detail: str = "Invalid emergency contact operation"):
        super().__init__(detail)
        self.error_code = "EMERGENCY_CONTACT_ERROR"

# Convenience functions for common cases
def user_not_found(user_id: Optional[int] = None):
    return UserNotFoundError(user_id)

def department_not_found(dept_id: Optional[int] = None):
    identifier = f"ID {dept_id}" if dept_id else None
    return ResourceNotFoundError("Department", identifier)

def role_not_found(role_id: Optional[int] = None):
    identifier = f"ID {role_id}" if role_id else None
    return ResourceNotFoundError("Role", identifier)

def leave_policy_not_found(policy_id: Optional[int] = None):
    identifier = f"ID {policy_id}" if policy_id else None
    return ResourceNotFoundError("Leave policy", identifier)

def shift_assignment_not_found(shift_id: Optional[int] = None):
    identifier = f"ID {shift_id}" if shift_id else None
    return ResourceNotFoundError("Shift assignment", identifier)

def shift_pattern_not_found(pattern_id: Optional[int] = None):
    identifier = f"ID {pattern_id}" if pattern_id else None
    return ResourceNotFoundError("Shift pattern", identifier)

def overtime_record_not_found(record_id: Optional[int] = None):
    identifier = f"ID {record_id}" if record_id else None
    return ResourceNotFoundError("Overtime record", identifier)

def leave_balance_not_found(balance_id: Optional[int] = None):
    identifier = f"ID {balance_id}" if balance_id else None
    return ResourceNotFoundError("Leave balance", identifier)

def holiday_not_found(holiday_id: Optional[int] = None):
    identifier = f"ID {holiday_id}" if holiday_id else None
    return ResourceNotFoundError("Holiday", identifier)

def leave_request_not_found(request_id: Optional[int] = None):
    identifier = f"ID {request_id}" if request_id else None
    return ResourceNotFoundError("Leave request", identifier)

def time_correction_not_found(correction_id: Optional[int] = None):
    identifier = f"ID {correction_id}" if correction_id else None
    return ResourceNotFoundError("Time correction", identifier)

def emergency_contact_not_found(contact_id: Optional[int] = None):
    identifier = f"ID {contact_id}" if contact_id else None
    return ResourceNotFoundError("Emergency contact", identifier)