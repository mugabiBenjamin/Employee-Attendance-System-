from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.core.enums import AttendanceStatus

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

    @field_validator('clock_out_time')
    def validate_clock_out(cls, clock_out_time: Optional[datetime], values: dict) -> Optional[datetime]:
        if clock_out_time and 'clock_in_time' in values and values['clock_in_time']:
            if clock_out_time <= values['clock_in_time']:
                raise ValueError('clock_out_time must be after clock_in_time')
        return clock_out_time

class AttendanceRecordCreate(AttendanceRecordBase):
    user_id: int
    clock_in_time: datetime
    ip_address: str
    location: Optional[str] = None
    status: AttendanceStatus = AttendanceStatus.PRESENT

class AttendanceRecordUpdate(BaseModel):
    clock_in_time: Optional[datetime] = None
    clock_out_time: Optional[datetime] = None
    break_duration: Optional[int] = Field(None, ge=0)
    total_hours: Optional[float] = Field(None, ge=0)
    overtime_hours: Optional[float] = Field(None, ge=0)
    status: Optional[str] = None
    location: Optional[str] = Field(None, max_length=255)

    @field_validator('clock_out_time')
    def validate_clock_out(cls, clock_out_time: Optional[datetime], values: dict) -> Optional[datetime]:
        if clock_out_time and 'clock_in_time' in values and values['clock_in_time']:
            if clock_out_time <= values['clock_in_time']:
                raise ValueError('clock_out_time must be after clock_in_time')
        return clock_out_time

class AttendanceRecordOut(AttendanceRecordBase):
    attendance_id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)