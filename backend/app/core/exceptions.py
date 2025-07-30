from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional, Dict, Any

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

class DatabaseError(SQLAlchemyError):
    """Database operation failures."""
    def __init__(self, message: str = "Database operation failed", original_error: Optional[Exception] = None):
        super().__init__(message)
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
    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="PERMISSION_DENIED"
        )

class ValidationError(BaseCustomException):
    """Input validation errors."""
    def __init__(self, detail: str = "Invalid input data", field: Optional[str] = None):
        error_detail = f"{field}: {detail}" if field else detail
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
    def __init__(self, detail: str = "Resource conflict"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_409_CONFLICT,
            error_code="RESOURCE_CONFLICT"
        )

class BusinessLogicError(BaseCustomException):
    """Business rule violations."""
    def __init__(self, detail: str = "Business rule violation"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="BUSINESS_LOGIC_ERROR"
        )

# Specific domain exceptions
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

# Convenience functions for common cases
def user_not_found(user_id: Optional[int] = None):
    identifier = f"ID {user_id}" if user_id else None
    return ResourceNotFoundError("User", identifier)

def department_not_found(dept_id: Optional[int] = None):
    identifier = f"ID {dept_id}" if dept_id else None
    return ResourceNotFoundError("Department", identifier)

def role_not_found(role_id: Optional[int] = None):
    identifier = f"ID {role_id}" if role_id else None
    return ResourceNotFoundError("Role", identifier)

def leave_policy_not_found(policy_id: Optional[int] = None):
    identifier = f"ID {policy_id}" if policy_id else None
    return ResourceNotFoundError("Leave policy", identifier)