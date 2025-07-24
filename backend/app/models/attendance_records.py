from typing import Optional
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import SQLModel, Field
from datetime import datetime, date as dt, timezone
from sqlalchemy.dialects.postgresql import ENUM, INET
from sqlalchemy.sql import func

# Define the attendance_status enum for PostgreSQL
attendance_status = ENUM(
    'present', 'absent', 'late', 'early_departure', 'on_leave', 'half_day', 'sick',
    name='attendance_status',
    create_type=True
)

class AttendanceRecords(SQLModel, table=True):
    attendance_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", nullable=False)
    clock_in_time: datetime = Field(nullable=False)
    clock_out_time: Optional[datetime] = Field(default=None)
    break_duration: int = Field(default=0, ge=0)
    total_hours: Optional[float] = Field(default=None, ge=0)
    overtime_hours: float = Field(default=0, ge=0)
    date: dt = Field(default_factory=dt.today)
    status: str = Field(default="present", sa_type=attendance_status)
    ip_address: Optional[str] = Field(default=None, sa_type=INET)
    location: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = Field(
        sa_column_kwargs={"server_default": func.current_timestamp(), "onupdate": func.current_timestamp()}
    )
    
    __table_args__ = (
        CheckConstraint("break_duration >= 0", name="break_duration_non_negative"),
        CheckConstraint("total_hours IS NULL OR total_hours >= 0", name="total_hours_non_negative"),
        CheckConstraint("overtime_hours >= 0", name="overtime_hours_non_negative"),
        CheckConstraint("clock_out_time IS NULL OR clock_out_time > clock_in_time", name="clock_times_valid"),
        UniqueConstraint("user_id", "date", name="unique_user_date"),
    )