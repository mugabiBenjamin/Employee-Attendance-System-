from datetime import datetime
from typing import Optional, List
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from fastapi import UploadFile
from app.core.config import settings
from app.core.exceptions import FileUploadError
import os

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

def calculate_overtime_hours(total_hours: float, standard_hours: float = 8.0) -> float:
    """Calculate overtime hours based on total hours exceeding standard hours."""
    overtime = max(0, total_hours - standard_hours)
    return round(overtime, 2)

def validate_file_upload(file: UploadFile, allowed_extensions: List[str] = settings.ALLOWED_EXTENSIONS, max_size: int = settings.MAX_FILE_SIZE) -> None:
    """Validate file upload based on extension and size."""
    file_ext = file.filename.split('.')[-1].lower() if '.' in file.filename else ''
    if file_ext not in allowed_extensions:
        raise FileUploadError(detail=f"File extension '{file_ext}' not allowed. Allowed: {', '.join(allowed_extensions)}")
    if file.size > max_size:
        raise FileUploadError(detail=f"File size exceeds limit of {max_size / (1024 * 1024)} MB")

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
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(settings.DEFAULT_TIMEZONE)).replace(hour=0, minute=0, second=0, microsecond=0)