from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import ENUM

# Define the correction_status enum for PostgreSQL
correction_status = ENUM(
    'draft', 'under_review', 'approved', 'rejected', 'cancelled', 'completed',
    name='correction_status',
    create_type=True
)

class TimeCorrectionBase(SQLModel):
    attendance_id: int = Field(foreign_key="attendancerecords.attendance_id", index=True)
    user_id: int = Field(foreign_key="users.user_id", index=True)
    original_clock_in: Optional[datetime] = Field(default=None)
    original_clock_out: Optional[datetime] = Field(default=None)
    corrected_clock_in: Optional[datetime] = Field(default=None)
    corrected_clock_out: Optional[datetime] = Field(default=None)
    reason: str
    status: str = Field(default="draft", sa_type=correction_status)
    approved_by: Optional[int] = Field(default=None, foreign_key="users.user_id", nullable=True)
    approved_at: Optional[datetime] = Field(default=None)

class TimeCorrection(TimeCorrectionBase, table=True):
    correction_id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TimeCorrectionCreate(TimeCorrectionBase):
    pass

class TimeCorrectionUpdate(SQLModel):
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