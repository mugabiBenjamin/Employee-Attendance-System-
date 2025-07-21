from typing import Optional
from pydantic import BaseModel
from datetime import datetime, date

class AttendanceBase(BaseModel):
    user_id: int
    clock_in_time: datetime
    clock_out_time: Optional[datetime] = None
    break_duration: int = 0
    date: date
    status: str = "present"
    ip_address: Optional[str] = None
    location: Optional[str] = None

class AttendanceCreate(AttendanceBase):
    pass

class AttendanceUpdate(BaseModel):
    clock_out_time: Optional[datetime] = None
    break_duration: Optional[int] = None
    status: Optional[str] = None
    ip_address: Optional[str] = None
    location: Optional[str] = None

class AttendanceOut(AttendanceBase):
    attendance_id: int
    total_hours: Optional[float] = None
    overtime_hours: float = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True