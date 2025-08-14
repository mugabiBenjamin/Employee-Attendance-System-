from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class LeaveBalanceBase(BaseModel):
    user_id: int
    leave_type: str
    allocated_days: int = Field(0, ge=0)
    used_days: int = Field(0, ge=0)
    carried_forward: int = Field(0, ge=0)
    year: int = Field(..., ge=2020, le=2050)
    is_active: bool = True
    deleted_at: Optional[datetime] = None

class LeaveBalanceCreate(LeaveBalanceBase):
    pass

class LeaveBalanceUpdate(BaseModel):
    user_id: int
    leave_type: str
    balance: float
    last_updated: datetime
    allocated_days: Optional[int] = Field(None, ge=0)
    used_days: Optional[int] = Field(None, ge=0)
    carried_forward: Optional[int] = Field(None, ge=0)
    year: Optional[int] = Field(None, ge=2020, le=2050)
    is_active: Optional[bool] = None

class LeaveBalanceOut(LeaveBalanceBase):
    balance_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)