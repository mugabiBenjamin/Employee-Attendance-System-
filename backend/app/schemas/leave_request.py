from datetime import datetime, date, timezone
import re
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator, HttpUrl
from app.core.enums import LeaveRequestStatus, LeaveType
from app.core.exceptions import ValidationError

class LeaveRequestBase(BaseModel):
    leave_type: LeaveType
    start_date: date
    end_date: date
    days_requested: int = Field(..., gt=0)
    reason: Optional[str] = None
    status: LeaveRequestStatus = LeaveRequestStatus.UNDER_REVIEW
    comments: Optional[str] = None
    attachment_url: Optional[HttpUrl] = Field(None, max_length=500)
    is_active: bool = True

    @field_validator('end_date')
    @classmethod
    def validate_end_date(cls, end_date: date, info: dict) -> date:
        if 'start_date' in info.data and info.data['start_date']:
            if end_date < info.data['start_date']:
                raise ValidationError(detail="end_date must be on or after start_date")
        return end_date

    @field_validator('days_requested')
    @classmethod
    def validate_days_requested(cls, days: int, info: dict) -> int:
        if 'start_date' in info.data and 'end_date' in info.data:
            start_date = info.data['start_date']
            end_date = info.data['end_date']
            if start_date and end_date:
                expected_days = (end_date - start_date).days + 1
                if days != expected_days:
                    raise ValidationError(detail=f"days_requested must equal {expected_days}")
        return days

class LeaveRequestCreate(LeaveRequestBase):
    user_id: int
    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: Optional[str] = None
    attachment_url: Optional[HttpUrl] = Field(None, max_length=500)

class LeaveRequestUpdate(BaseModel):
    leave_type: Optional[LeaveType] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    days_requested: Optional[int] = Field(None, gt=0)
    reason: Optional[str] = None
    status: Optional[LeaveRequestStatus] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    comments: Optional[str] = None
    attachment_url: Optional[HttpUrl] = Field(None, max_length=500)
    is_active: Optional[bool] = None

    @field_validator('end_date')
    @classmethod
    def validate_end_date(cls, end_date: Optional[date], info: dict) -> Optional[date]:
        if end_date and 'start_date' in info.data and info.data['start_date']:
            if end_date < info.data['start_date']:
                raise ValidationError(detail="end_date must be on or after start_date")
        return end_date

    @field_validator('days_requested')
    @classmethod
    def validate_days_requested(cls, days: Optional[int], info: dict) -> Optional[int]:
        if days is not None and 'start_date' in info.data and 'end_date' in info.data:
            start_date = info.data['start_date']
            end_date = info.data['end_date']
            if start_date and end_date:
                expected_days = (end_date - start_date).days + 1
                if days != expected_days:
                    raise ValidationError(detail=f"days_requested must equal {expected_days}")
        return days

    @field_validator('approved_by')
    @classmethod
    def validate_approved_by(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValidationError(detail="Invalid approved_by ID")
        return value

    @field_validator('approved_at', mode='before')
    @classmethod
    def validate_approved_at(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return value
        if isinstance(value, str):
            iso_format_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2}|Z)?$'
            if not re.match(iso_format_pattern, value):
                raise ValidationError(detail="Invalid datetime format for approved_at. Must be ISO 8601 (e.g., '2025-08-14T12:00:00Z').")
            try:
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                raise ValidationError(detail="Invalid datetime value for approved_at.")
        if value.tzinfo is None:
            raise ValidationError(detail="approved_at must include timezone")
        if value > datetime.now(timezone.utc):
            raise ValidationError(detail="approved_at cannot be in the future")
        return value

class LeaveRequestOut(LeaveRequestBase):
    leave_id: int
    user_id: int
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_validator('leave_id', 'user_id', 'approved_by')
    @classmethod
    def validate_ids(cls, value: Optional[int], info: dict) -> Optional[int]:
        if value is not None and value <= 0:
            field = info.field_name
            raise ValidationError(detail=f"Invalid {field}")
        return value

    @field_validator('created_at', 'updated_at', 'approved_at')
    @classmethod
    def validate_timezone(cls, value: Optional[datetime], info: dict) -> Optional[datetime]:
        if value and value.tzinfo is None:
            raise ValidationError(detail=f"{info.field_name.capitalize()} must include timezone")
        return value

    model_config = ConfigDict(from_attributes=True)

class LeaveApprovalUpdate(BaseModel):
    status: LeaveRequestStatus
    comments: Optional[str] = None