from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.core.enums import LeaveType
from app.core.exceptions import ValidationError

class LeavePolicyDetails(BaseModel):
    policy_id: Optional[int] = None
    employee_type: Optional[str] = None
    leave_type: Optional[LeaveType] = None
    annual_allocation: Optional[float] = None
    carry_forward_limit: Optional[float] = None
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class LeaveBalanceBase(BaseModel):
    user_id: int
    leave_type: LeaveType
    allocated_days: float = Field(0, ge=0)
    used_days: float = Field(0, ge=0)
    carried_forward: float = Field(0, ge=0)
    year: int = Field(..., ge=2020, le=2050)
    version: int = Field(1, ge=1)
    is_active: bool = True

    @field_validator('user_id')
    @classmethod
    def validate_user_id(cls, value: int) -> int:
        if value <= 0:
            raise ValidationError(detail="Invalid user_id")
        return value

class LeaveBalanceCreate(LeaveBalanceBase):
    user_id: int
    leave_type: LeaveType
    allocated_days: float = Field(0, ge=0)
    used_days: float = Field(0, ge=0)
    carried_forward: float = Field(0, ge=0)
    year: int = Field(..., ge=2020, le=2050)
    version: int = Field(1, ge=1)

class LeaveBalanceUpdate(BaseModel):
    allocated_days: Optional[float] = Field(None, ge=0)
    used_days: Optional[float] = Field(None, ge=0)
    carried_forward: Optional[float] = Field(None, ge=0)
    version: Optional[int] = Field(None, ge=1)
    is_active: Optional[bool] = None
    deleted_at: Optional[datetime] = None

    @field_validator('is_active')
    @classmethod
    def validate_is_active(cls, value: Optional[bool], info) -> Optional[bool]:
        if value is False and not (info.data.get('deleted_at')):
            raise ValidationError(detail="Cannot set is_active to False without setting deleted_at")
        return value

class LeaveBalanceOut(LeaveBalanceBase):
    balance_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    policy_details: LeavePolicyDetails = Field(default_factory=LeavePolicyDetails)
    pending_days: float = Field(0, ge=0)

    @field_validator('balance_id', 'version')
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
        json_encoders={datetime: lambda v: v.isoformat()}
    )