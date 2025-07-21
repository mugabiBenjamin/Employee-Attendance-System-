from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, date

class Attendance(SQLModel, table=True):
    attendance_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", nullable=False)
    clock_in_time: datetime = Field(nullable=False)
    clock_out_time: Optional[datetime] = Field(default=None)
    break_duration: int = Field(default=0, ge=0)
    total_hours: Optional[float] = Field(default=None, ge=0)
    overtime_hours: float = Field(default=0, ge=0)
    date: date = Field(default_factory=date.today)
    status: str = Field(default="present")
    ip_address: Optional[str] = Field(default=None)
    location: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)