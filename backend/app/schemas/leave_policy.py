
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field

class LeavePolicyBase(BaseModel):
    employee_type: str
    leave_type: str
    annual_allocation: int = Field(0, ge=0)
    carry_forward_limit: int = Field(0, ge=0)
    max_consecutive_days: Optional[int] = Field(None, gt=0)
    requires_approval: bool = True
    approval_levels: int = Field(1, ge=1, le=5)
    accrual_rate: float = Field(0, ge=0)
    effective_from: date
    effective_to: Optional[date] = None

class LeavePolicyCreate(LeavePolicyBase):
    pass

class LeavePolicyUpdate(BaseModel):
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
    
    class Config:
        from_attributes = True