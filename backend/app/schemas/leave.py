from typing import Optional
from pydantic import BaseModel
from datetime import datetime, date

class LeaveRequestBase(BaseModel):
    user_id: int
    leave_type: str
    start_date: date
    end_date: date
    days_requested: int
    reason: Optional[str] = None
    status: str = "draft"
    attachment_url: Optional[str] = None

class LeaveRequestCreate(LeaveRequestBase):
    pass

class LeaveRequestUpdate(BaseModel):
    leave_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    days_requested: Optional[int] = None
    reason: Optional[str] = None
    status: Optional[str] = None
    comments: Optional[str] = None
    attachment_url: Optional[str] = None

class LeaveRequestOut(LeaveRequestBase):
    leave_id: int
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    comments: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class LeaveBalanceBase(BaseModel):
    user_id: int
    leave_type: str
    allocated_days: int = 0
    used_days: int = 0
    carried_forward: int = 0
    year: int

class LeaveBalanceCreate(LeaveBalanceBase):
    pass

class LeaveBalanceUpdate(BaseModel):
    allocated_days: Optional[int] = None
    used_days: Optional[int] = None
    carried_forward: Optional[int] = None
    year: Optional[int] = None

class LeaveBalanceOut(LeaveBalanceBase):
    balance_id: int
    updated_at: datetime

    class Config:
        from_attributes = True