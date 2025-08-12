from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.core.enums import CorrectionStatus

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
    attendance_id: int
    user_id: int
    original_clock_in: Optional[datetime] = None
    original_clock_out: Optional[datetime] = None
    corrected_clock_in: Optional[datetime] = None
    corrected_clock_out: Optional[datetime] = None
    reason: str
    status: CorrectionStatus = CorrectionStatus.DRAFT

class TimeCorrectionUpdate(BaseModel):
    corrected_clock_in: Optional[datetime] = None
    corrected_clock_out: Optional[datetime] = None
    reason: Optional[str] = None
    status: Optional[CorrectionStatus] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None

class TimeCorrectionOut(TimeCorrectionBase):
    correction_id: int
    created_at: datetime
    user_id: int
    original_clock_in: Optional[datetime] = None
    original_clock_out: Optional[datetime] = None
    corrected_clock_in: Optional[datetime] = None
    corrected_clock_out: Optional[datetime] = None
    reason: str
    status: CorrectionStatus
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    attendance_id: int
    

class TimeCorrectionApproval(BaseModel):
    status: str
    
    model_config = ConfigDict(from_attributes=True)