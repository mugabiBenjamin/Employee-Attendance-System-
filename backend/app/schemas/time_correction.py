
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class TimeCorrectionBase(BaseModel):
    attendance_id: int
    user_id: int
    original_clock_in: Optional[datetime] = None
    original_clock_out: Optional[datetime] = None
    corrected_clock_in: Optional[datetime] = None
    corrected_clock_out: Optional[datetime] = None
    reason: str
    status: str = 'draft'
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None

class TimeCorrectionCreate(TimeCorrectionBase):
    pass

class TimeCorrectionUpdate(BaseModel):
    original_clock_in: Optional[datetime] = None
    original_clock_out: Optional[datetime] = None
    corrected_clock_in: Optional[datetime] = None
    corrected_clock_out: Optional[datetime] = None
    reason: Optional[str] = None
    status: Optional[str] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None

class TimeCorrectionOut(TimeCorrectionBase):
    correction_id: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)