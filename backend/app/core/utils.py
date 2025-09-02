from datetime import datetime, time, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from fastapi import UploadFile, Request
from app.core.config import settings
from app.core.exceptions import FileUploadError, DatabaseError
import os
from zoneinfo import ZoneInfo
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from decimal import Decimal
from uuid import UUID
import base64

logger = logging.getLogger(__name__)

class TimeCalculation(BaseModel):
    clock_in: Optional[datetime] = None
    clock_out: Optional[datetime] = None
    break_duration: int = Field(0, ge=0)  # in minutes

    model_config = ConfigDict(from_attributes=True)

def calculate_total_hours(clock_in: datetime, clock_out: Optional[datetime] = None, break_duration: int = 0) -> Optional[float]:
    """Calculate total hours between clock_in and clock_out, subtracting break duration."""
    if not clock_out or clock_in >= clock_out:
        return None
    duration = (clock_out - clock_in).total_seconds() / 3600  # Convert to hours
    break_hours = break_duration / 60  # Convert minutes to hours
    total_hours = max(0, duration - break_hours)
    return round(total_hours, 2)

def calculate_overtime_hours(total_hours: float, standard_hours: float = settings.OVERTIME_THRESHOLD) -> float:
    """Calculate overtime hours based on total hours exceeding standard hours."""
    overtime = max(0, total_hours - standard_hours)
    return round(overtime, 2)

def calculate_shift_hours(start_time: time, end_time: time, is_overnight: bool = False) -> float:
    """Calculate shift duration in hours based on start_time, end_time, and is_overnight."""
    # Convert time objects to datetime for calculation (use a dummy date)
    dummy_date = datetime(2023, 1, 1)
    start_dt = datetime.combine(dummy_date, start_time)
    end_dt = datetime.combine(dummy_date, end_time)
    
    if is_overnight and end_time < start_time:
        # Add 1 day to end_dt for overnight shifts
        end_dt += timedelta(days=1)
    
    duration = (end_dt - start_dt).total_seconds() / 3600  # Convert to hours
    return round(max(0, duration), 2)

async def validate_file_upload(file: UploadFile, allowed_extensions: List[str] = settings.ALLOWED_EXTENSIONS, max_size: int = settings.MAX_FILE_SIZE) -> None:
    """Validate file upload based on extension and size by reading the stream."""
    file_ext = file.filename.split('.')[-1].lower() if '.' in file.filename else ''
    if file_ext not in allowed_extensions:
        raise FileUploadError(detail=f"File extension '{file_ext}' not allowed. Allowed: {', '.join(allowed_extensions)}")
    
    # Check file size by reading stream
    try:
        content = await file.read()
        file_size = len(content)
        if file_size > max_size:
            raise FileUploadError(detail=f"File size exceeds limit of {max_size / (1024 * 1024)} MB")
        # Reset file pointer to start
        await file.seek(0)
    except Exception as e:
        raise FileUploadError(detail=f"Failed to validate file size: {str(e)}")

async def save_uploaded_file(file: UploadFile, upload_folder: str = settings.UPLOAD_FOLDER) -> str:
    """Save uploaded file to the specified folder and return its path."""
    try:
        os.makedirs(upload_folder, exist_ok=True)
        file_path = Path(upload_folder) / file.filename
        with file_path.open("wb") as f:
            content = await file.read()
            f.write(content)
        return str(file_path)
    except Exception as e:
        raise FileUploadError(detail=f"Failed to save file: {str(e)}")

def is_date_range_valid(start_date: datetime, end_date: datetime) -> bool:
    """Validate that end_date is not before start_date."""
    return end_date >= start_date

def format_datetime(dt: Optional[datetime]) -> Optional[str]:
    """Format datetime to ISO string or return None if datetime is None."""
    return dt.isoformat() if dt else None

def get_current_date() -> datetime:
    """Return current date in the configured timezone."""
    return datetime.now(ZoneInfo(settings.DEFAULT_TIMEZONE)).replace(hour=0, minute=0, second=0, microsecond=0)

def get_request_id(request: Request) -> Optional[str]:
    """Safely extract request_id from request state."""
    try:
        if hasattr(request, 'state') and hasattr(request.state, 'request_id'):
            return request.state.request_id
        return None
    except Exception as e:
        logger.warning(f"Failed to extract request_id: {str(e)}")
        return None

async def get_users_with_permission(permission: str, db: AsyncSession) -> List[Users]:
    """Get all users who have a specific permission through their roles."""
    try:
        query = select(Users).join(
            UserRoles, UserRoles.user_id == Users.user_id
        ).join(
            Roles, Roles.role_id == UserRoles.role_id
        ).where(
            and_(
                Users.is_active == True,
                Users.deleted_at == None,
                UserRoles.is_active == True,
                UserRoles.deleted_at == None,
                Roles.is_active == True,
                Roles.deleted_at == None,
                Roles.permissions.contains({permission: True})
            )
        )
        result = await db.execute(query)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error getting users with permission {permission}: {str(e)}", exc_info=True)
        raise DatabaseError(f"Failed to retrieve users with permission '{permission}': {str(e)}")

def serialize_model_for_logging(model) -> Dict[str, Any]:
    """Convert SQLAlchemy model to JSON-serializable dict."""
    result = {}
    for column in model.__table__.columns:
        value = getattr(model, column.name)
        result[column.name] = _serialize_value_for_logging(value)
    return result

def serialize_dict_for_logging(data_dict: dict) -> Dict[str, Any]:
    """Convert dictionary with potentially non-serializable values to JSON-serializable dict."""
    if not data_dict:
        return {}
        
    result = {}
    for key, value in data_dict.items():
        result[key] = _serialize_value_for_logging(value)
    return result

def _serialize_value_for_logging(value: Any) -> Any:
    """Helper function to serialize individual values for logging."""
    if value is None:
        return None
    elif hasattr(value, 'isoformat'):  # datetime/date
        return value.isoformat()
    elif hasattr(value, 'value'):  # enum
        return value.value
    elif isinstance(value, Decimal):
        return str(value)  # Convert Decimal to string to preserve precision
    elif isinstance(value, UUID):
        return str(value)  # Convert UUID to string
    elif isinstance(value, (bytes, bytearray)):
        return base64.b64encode(value).decode('utf-8')  # Convert bytes to base64 string
    elif isinstance(value, memoryview):
        return base64.b64encode(value.tobytes()).decode('utf-8')  # Convert memoryview to base64
    elif isinstance(value, (int, float, str, bool)):
        return value  # Already JSON-serializable
    else:
        return str(value)  # Fallback to string representation