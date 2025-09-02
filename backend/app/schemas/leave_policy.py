from datetime import datetime, date, timezone
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.core.enums import EmployeeType, LeaveType
from app.core.exceptions import ValidationError

class LeavePolicyBase(BaseModel):
    employee_type: EmployeeType
    leave_type: LeaveType
    annual_allocation: float = Field(0, ge=0)
    carry_forward_limit: float = Field(0, ge=0)
    max_consecutive_days: Optional[int] = Field(None, gt=0)
    requires_approval: bool = True
    approval_levels: int = Field(1, ge=1, le=5)
    accrual_rate: float = Field(0, ge=0)
    effective_from: date
    effective_to: Optional[date] = None
    version: int = Field(1, ge=1)

    @field_validator('effective_from', 'effective_to')
    @classmethod
    def validate_dates(cls, value: Optional[date], info: dict) -> Optional[date]:
        if value and value > datetime.now(timezone.utc).date():
            raise ValidationError(detail=f"{info.field_name.capitalize()} cannot be in the future")
        return value

    @field_validator('effective_to')
    @classmethod
    def validate_effective_to(cls, value: Optional[date], values: dict) -> Optional[date]:
        if value and 'effective_from' in values and values['effective_from'] and value < values['effective_from']:
            raise ValidationError(detail="effective_to must be on or after effective_from")
        return value

class LeavePolicyCreate(LeavePolicyBase):
    employee_type: EmployeeType
    leave_type: LeaveType
    annual_allocation: float = Field(0, ge=0)
    carry_forward_limit: float = Field(0, ge=0)
    max_consecutive_days: Optional[int] = Field(None, gt=0)
    requires_approval: bool = True
    approval_levels: int = Field(1, ge=1, le=5)
    accrual_rate: float = Field(0, ge=0)
    effective_from: date
    effective_to: Optional[date] = None
    version: int = Field(1, ge=1)

class LeavePolicyUpdate(BaseModel):
    employee_type: Optional[EmployeeType] = None
    leave_type: Optional[LeaveType] = None
    annual_allocation: Optional[float] = Field(None, ge=0)
    carry_forward_limit: Optional[float] = Field(None, ge=0)
    max_consecutive_days: Optional[int] = Field(None, gt=0)
    requires_approval: Optional[bool] = None
    approval_levels: Optional[int] = Field(None, ge=1, le=5)
    accrual_rate: Optional[float] = Field(None, ge=0)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    version: Optional[int] = Field(None, ge=1)

    @field_validator('effective_from', 'effective_to')
    @classmethod
    def validate_dates(cls, value: Optional[date], info: dict) -> Optional[date]:
        if value and value > datetime.now(timezone.utc).date():
            raise ValidationError(detail=f"{info.field_name.capitalize()} cannot be in the future")
        return value

    @field_validator('effective_to')
    @classmethod
    def validate_effective_to(cls, value: Optional[date], values: dict) -> Optional[date]:
        if value and 'effective_from' in values and values['effective_from'] and value < values['effective_from']:
            raise ValidationError(detail="effective_to must be on or after effective_from")
        return value

class LeavePolicyOut(LeavePolicyBase):
    policy_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_validator('policy_id', 'version')
    @classmethod
    def validate_ids(cls, value: int, info: dict) -> int:
        if value <= 0:
            raise ValidationError(detail=f"Invalid {info.field_name}")
        return value

    @field_validator('created_at', 'updated_at')
    @classmethod
    def validate_timezone(cls, value: Optional[datetime], info: dict) -> Optional[datetime]:
        if value and value.tzinfo is None:
            raise ValidationError(detail=f"{info.field_name.capitalize()} must include timezone")
        return value

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
        },
        arbitrary_types_allowed=True,
    )