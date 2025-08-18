from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from app.core.enums import LeaveType

class LeaveBalanceBase(BaseModel):
    user_id: int
    leave_type: LeaveType
    allocated_days: float = Field(0, ge=0)
    used_days: float = Field(0, ge=0)
    carried_forward: float = Field(0, ge=0)
    year: int = Field(..., ge=2020, le=2050)
    is_active: bool = True

class LeaveBalanceCreate(LeaveBalanceBase):
    user_id: int
    leave_type: LeaveType
    allocated_days: float = Field(0, ge=0)
    used_days: float = Field(0, ge=0)
    carried_forward: float = Field(0, ge=0)

class LeaveBalanceUpdate(BaseModel):
    allocated_days: Optional[float] = Field(None, ge=0)
    used_days: Optional[float] = Field(None, ge=0)
    carried_forward: Optional[float] = Field(None, ge=0)
    is_active: Optional[bool] = None

class LeaveBalanceOut(LeaveBalanceBase):
    balance_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    policy_details: Dict[str, Any] = {}
    
    model_config = ConfigDict(from_attributes=True)