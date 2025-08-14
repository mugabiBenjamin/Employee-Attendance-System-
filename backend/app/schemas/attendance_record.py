from datetime import datetime, date, timezone
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.core.enums import AttendanceStatus
from app.core.exceptions import ValidationError
import re

class AttendanceRecordBase(BaseModel):
    clock_in_time: datetime
    clock_out_time: Optional[datetime] = None
    break_duration: int = Field(0, ge=0)
    total_hours: Optional[float] = Field(None, ge=0)
    overtime_hours: float = Field(0, ge=0)
    date: date
    status: str = 'present'
    ip_address: Optional[str] = None
    location: Optional[str] = Field(None, max_length=255)
    is_active: bool = True

    @field_validator('clock_in_time', 'clock_out_time', mode='before')
    @classmethod
    def validate_datetime_format(cls, value):
        if value is None:
            return value
        if isinstance(value, str):
            # Check ISO 8601 format
            iso_format_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2}|Z)?$'
            if not re.match(iso_format_pattern, value):
                raise ValidationError(detail=f"Invalid datetime format. Must be ISO 8601 (e.g., '2025-08-14T12:00:00Z').")
            try:
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                raise ValidationError(detail="Invalid datetime value.")
        # Ensure datetime is not in the future
        if value > datetime.now(value.tzinfo or timezone.utc):
            raise ValidationError(detail="Datetime cannot be in the future.")
        return value

    @field_validator('clock_out_time')
    @classmethod
    def validate_clock_out(cls, clock_out_time, info):
        if clock_out_time and hasattr(info, 'data') and 'clock_in_time' in info.data:
            clock_in_time = info.data['clock_in_time']
            if clock_in_time and clock_out_time <= clock_in_time:
                raise ValidationError(detail='clock_out_time must be after clock_in_time')
        return clock_out_time

    @field_validator('date')
    @classmethod
    def validate_date(cls, value):
        # Ensure date is not in the future
        if value > date.today():
            raise ValidationError(detail="Date cannot be in the future.")
        return value

class AttendanceRecordCreate(AttendanceRecordBase):
    user_id: int
    clock_in_time: datetime
    ip_address: str
    location: Optional[str] = None
    status: AttendanceStatus = AttendanceStatus.PRESENT

class AttendanceRecordUpdate(BaseModel):
    clock_in_time: Optional[datetime] = None
    clock_out_time: Optional[datetime] = None
    break_duration: Optional[int] = Field(None, ge=0)
    total_hours: Optional[float] = Field(None, ge=0)
    overtime_hours: Optional[float] = Field(None, ge=0)
    status: Optional[str] = None
    location: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None

    @field_validator('clock_in_time', 'clock_out_time', mode='before')
    @classmethod
    def validate_datetime_format(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return value
        if isinstance(value, str):
            iso_format_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2}|Z)?$'
            if not re.match(iso_format_pattern, value):
                raise ValidationError(detail="Invalid datetime format. Must be ISO 8601 (e.g., '2025-08-14T12:00:00Z').")
            try:
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                raise ValidationError(detail="Invalid datetime value.")
        if value > datetime.now(value.tzinfo or timezone.utc):
            raise ValidationError(detail="Datetime cannot be in the future.")
        return value

    @field_validator('clock_out_time')
    @classmethod
    def validate_clock_out(cls, clock_out_time: Optional[datetime], info) -> Optional[datetime]:
        if clock_out_time and hasattr(info, 'data') and 'clock_in_time' in info.data:
            clock_in_time = info.data['clock_in_time']
            if clock_in_time and clock_out_time <= clock_in_time:
                raise ValidationError(detail='clock_out_time must be after clock_in_time')
        return clock_out_time

class AttendanceRecordOut(AttendanceRecordBase):
    attendance_id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)