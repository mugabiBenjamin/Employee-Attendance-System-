from typing import Optional, Literal
from pydantic import BaseModel
from datetime import datetime, date
from zoneinfo import ZoneInfo

class AttendanceBase(BaseModel):
    user_id: int
    clock_in_time: datetime  # Will include timezone info
    clock_out_time: Optional[datetime] = None  # Will include timezone info
    break_duration: int = 0
    date: date
    status: Literal["present", "absent", "late", "early_departure", "on_leave", "half_day", "sick"] = "present"
    ip_address: Optional[str] = None
    location: Optional[str] = None

class AttendanceCreate(AttendanceBase):
    pass

class AttendanceUpdate(BaseModel):
    clock_out_time: Optional[datetime] = None
    break_duration: Optional[int] = None
    status: Optional[Literal["present", "absent", "late", "early_departure", "on_leave", "half_day", "sick"]] = None
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