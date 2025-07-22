from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, date as dt, timezone
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.sql import func

# Define the attendance_status enum for PostgreSQL
attendance_status = ENUM(
    'present', 'absent', 'late', 'early_departure', 'on_leave', 'half_day', 'sick',
    name='attendance_status',
    create_type=True
)

class Attendance(SQLModel, table=True):
    attendance_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", nullable=False)
    clock_in_time: datetime = Field(nullable=False)
    clock_out_time: Optional[datetime] = Field(default=None)
    break_duration: int = Field(default=0, ge=0, sa_column_kwargs={"check": "break_duration >= 0"})
    total_hours: Optional[float] = Field(default=None, ge=0, sa_column_kwargs={"check": "total_hours IS NULL OR total_hours >= 0"})
    overtime_hours: float = Field(default=0, ge=0, sa_column_kwargs={"check": "overtime_hours >= 0"})
    date: dt = Field(default_factory=dt.today)
    status: str = Field(default="present", sa_type=attendance_status)
    ip_address: Optional[str] = Field(default=None, sa_type=func.inet)
    location: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"server_default": func.current_timestamp(), "onupdate": func.current_timestamp()}
    )
    __table_args__ = (
        {"schema": "public", "constraints": [
            {"name": "clock_times_valid", "check": "clock_out_time IS NULL OR clock_out_time > clock_in_time"},
            {"name": "unique_user_date", "unique": ["user_id", "date"]}
        ]},
    )