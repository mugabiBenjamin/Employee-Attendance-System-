from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field

class AttendanceRecordBase(BaseModel):
    clock_in_time: datetime
    clock_out_time: Optional[datetime] = None
    break_duration: int = Field(0, ge=0)
    total_hours: Optional[float] = Field(None, ge=0)
    overtime_hours: float = Field(0, ge=0)
    date: date
    status: str = 'present'
    ip_address: Optional[str] = None
    location: Optional[str] = Field(None, max_length=255)

class AttendanceRecordCreate(AttendanceRecordBase):
    user_id: int

class AttendanceRecordUpdate(BaseModel):
    clock_in_time: Optional[datetime] = None
    clock_out_time: Optional[datetime] = None
    break_duration: Optional[int] = Field(None, ge=0)
    total_hours: Optional[float] = Field(None, ge=0)
    overtime_hours: Optional[float] = Field(None, ge=0)
    status: Optional[str] = None
    location: Optional[str] = Field(None, max_length=255)

class AttendanceRecordOut(AttendanceRecordBase):
    attendance_id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True