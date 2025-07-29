
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class OvertimeRecordBase(BaseModel):
    attendance_id: int
    user_id: int
    overtime_hours: float = Field(..., gt=0)
    overtime_rate: float = Field(1.5, gt=0)
    overtime_amount: Optional[float] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None

class OvertimeRecordCreate(OvertimeRecordBase):
    user_id: int
    date: date
    overtime_hours: float
    description: Optional[str] = None

class OvertimeRecordUpdate(BaseModel):
    overtime_hours: Optional[float] = Field(None, gt=0)
    overtime_rate: Optional[float] = Field(None, gt=0)
    overtime_amount: Optional[float] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None

class OvertimeRecordOut(OvertimeRecordBase):
    overtime_id: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)