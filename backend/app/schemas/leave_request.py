
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field

class LeaveRequestBase(BaseModel):
    leave_type: str
    start_date: date
    end_date: date
    days_requested: int = Field(..., gt=0)
    reason: Optional[str] = None
    status: str = 'draft'
    comments: Optional[str] = None
    attachment_url: Optional[str] = Field(None, max_length=500)

class LeaveRequestCreate(LeaveRequestBase):
    user_id: int

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

class LeaveRequestOut(LeaveRequestBase):
    leave_id: int
    user_id: int
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True