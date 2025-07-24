from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

class DatabaseError(SQLAlchemyError):
    """Custom exception for database-related errors."""
    def __init__(self, message: str = "Database operation failed"):
        super().__init__(message)

class AuthenticationError(HTTPException):
    """Custom exception for authentication failures."""
    def __init__(self, detail: str = "Authentication failed", status_code: int = status.HTTP_401_UNAUTHORIZED):
        super().__init__(status_code=status_code, detail=detail, headers={"WWW-Authenticate": "Bearer"})

class AuthorizationError(HTTPException):
    """Custom exception for authorization/permission errors."""
    def __init__(self, detail: str = "Insufficient permissions", status_code: int = status.HTTP_403_FORBIDDEN):
        super().__init__(status_code=status_code, detail=detail)

class ValidationErrorCustom(HTTPException):
    """Custom exception for Pydantic V2 validation errors."""
    def __init__(self, detail: str = "Invalid input data", status_code: int = status.HTTP_422_UNPROCESSABLE_ENTITY):
        super().__init__(status_code=status_code, detail=detail)

class LeaveRequestError(HTTPException):
    """Custom exception for leave request-related errors."""
    def __init__(self, detail: str = "Invalid leave request", status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)

class AttendanceError(HTTPException):
    """Custom exception for attendance-related errors."""
    def __init__(self, detail: str = "Invalid attendance operation", status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)

class UserNotFoundError(HTTPException):
    """Custom exception for user not found errors."""
    def __init__(self, detail: str = "User not found", status_code: int = status.HTTP_404_NOT_FOUND):
        super().__init__(status_code=status_code, detail=detail)

class DepartmentNotFoundError(HTTPException):
    """Custom exception for department not found errors."""
    def __init__(self, detail: str = "Department not found", status_code: int = status.HTTP_404_NOT_FOUND):
        super().__init__(status_code=status_code, detail=detail)

class RoleNotFoundError(HTTPException):
    """Custom exception for role not found errors."""
    def __init__(self, detail: str = "Role not found", status_code: int = status.HTTP_404_NOT_FOUND):
        super().__init__(status_code=status_code, detail=detail)

class FileUploadError(HTTPException):
    """Custom exception for file upload errors."""
    def __init__(self, detail: str = "File upload failed", status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)