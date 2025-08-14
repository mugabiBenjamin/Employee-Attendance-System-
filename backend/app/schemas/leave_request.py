from datetime import datetime, date, timezone
import re
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.core.enums import LeaveRequestStatus
from app.core.exceptions import ValidationError

class LeaveRequestBase(BaseModel):
    leave_type: str
    start_date: date
    end_date: date
    days_requested: int = Field(..., gt=0)
    reason: Optional[str] = None
    status: str = 'draft'
    comments: Optional[str] = None
    attachment_url: Optional[str] = Field(None, max_length=500)

    @field_validator('start_date', 'end_date')
    def validate_dates(cls, value: date) -> date:
        if value > date.today():
            raise ValidationError(detail=f"{cls.__name__} date cannot be in the future.")
        return value

    @field_validator('end_date')
    def validate_end_date(cls, end_date: date, values: dict) -> date:
        if 'start_date' in values and values['start_date'] and end_date < values['start_date']:
            raise ValidationError(detail="end_date must be on or after start_date")
        return end_date

    @field_validator('days_requested')
    def validate_days_requested(cls, days: int, values: dict) -> int:
        if 'start_date' in values and 'end_date' in values and values['start_date'] and values['end_date']:
            expected_days = (values['end_date'] - values['start_date']).days + 1
            if days != expected_days:
                raise ValidationError(detail=f"days_requested must equal the number of days between start_date and end_date ({expected_days})")
        return days

class LeaveRequestCreate(LeaveRequestBase):
    user_id: int
    leave_type: str
    start_date: date
    end_date: date
    reason: Optional[str] = None
    status: LeaveRequestStatus = LeaveRequestStatus.UNDER_REVIEW

class LeaveRequestUpdate(BaseModel):
    leave_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    days_requested: Optional[int] = Field(None, gt=0)
    reason: Optional[str] = None
    status: Optional[str] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    comments: Optional[str] = None
    attachment_url: Optional[str] = Field(None, max_length=500)

    @field_validator('start_date', 'end_date')
    def validate_dates(cls, value: Optional[date]) -> Optional[date]:
        if value and value > date.today():
            raise ValidationError(detail=f"{cls.__name__} date cannot be in the future.")
        return value

    @field_validator('end_date')
    def validate_end_date(cls, end_date: Optional[date], values: dict) -> Optional[date]:
        if end_date and 'start_date' in values and values['start_date']:
            if end_date < values['start_date']:
                raise ValidationError(detail="end_date must be on or after start_date")
        return end_date

    @field_validator('days_requested')
    def validate_days_requested(cls, days: Optional[int], values: dict) -> Optional[int]:
        if days is not None and 'start_date' in values and 'end_date' in values and values['start_date'] and values['end_date']:
            expected_days = (values['end_date'] - values['start_date']).days + 1
            if days != expected_days:
                raise ValidationError(detail=f"days_requested must equal the number of days between start_date and end_date ({expected_days})")
        return days

    @field_validator('approved_at', mode='before')
    def validate_approved_at(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return value
        if isinstance(value, str):
            iso_format_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2}|Z)?$'
            if not re.match(iso_format_pattern, value):
                raise ValidationError(detail=f"Invalid datetime format for approved_at. Must be ISO 8601 (e.g., '2025-08-14T12:00:00Z').")
            try:
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                raise ValidationError(detail="Invalid datetime value for approved_at.")
        if value > datetime.now(value.tzinfo or timezone.utc):
            raise ValidationError(detail="approved_at cannot be in the future.")
        return value

class LeaveRequestOut(LeaveRequestBase):
    leave_id: int
    user_id: int
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)