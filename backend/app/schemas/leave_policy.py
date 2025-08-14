from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.core.enums import EmployeeType, LeaveType

class LeavePolicyBase(BaseModel):
    employee_type: EmployeeType
    leave_type: LeaveType
    annual_allocation: int = Field(0, ge=0)
    carry_forward_limit: int = Field(0, ge=0)
    max_consecutive_days: Optional[int] = Field(None, gt=0)
    requires_approval: bool = True
    approval_levels: int = Field(1, ge=1, le=5)
    accrual_rate: float = Field(0, ge=0)
    effective_from: date
    effective_to: Optional[date] = None

class LeavePolicyCreate(LeavePolicyBase):
    employee_type: EmployeeType
    leave_type: LeaveType
    annual_allocation: int = Field(0, ge=0)
    carry_forward_limit: int = Field(0, ge=0)
    max_consecutive_days: Optional[int] = Field(None, gt=0)
    requires_approval: bool = True
    approval_levels: int = Field(1, ge=1, le=5)
    accrual_rate: float = Field(0, ge=0)
    effective_from: date
    effective_to: Optional[date] = None

class LeavePolicyUpdate(BaseModel):
    employee_type: Optional[EmployeeType] = None
    leave_type: Optional[LeaveType] = None
    annual_allocation: Optional[int] = Field(None, ge=0)
    carry_forward_limit: Optional[int] = Field(None, ge=0)
    max_consecutive_days: Optional[int] = Field(None, gt=0)
    requires_approval: Optional[bool] = None
    approval_levels: Optional[int] = Field(None, ge=1, le=5)
    accrual_rate: Optional[float] = Field(None, ge=0)
    effective_to: Optional[date] = None

class LeavePolicyOut(LeavePolicyBase):
    policy_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)