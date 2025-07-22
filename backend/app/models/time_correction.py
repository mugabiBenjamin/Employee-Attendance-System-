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

class TimeCorrection(SQLModel, table=True):
    correction_id: Optional[int] = Field(default=None, primary_key=True)
    attendance_id: int = Field(foreign_key="attendance_records.attendance_id", nullable=False)
    user_id: int = Field(foreign_key="users.user_id", nullable=False)
    original_clock_in: Optional[datetime] = Field(default=None)
    original_clock_out: Optional[datetime] = Field(default=None)
    corrected_clock_in: Optional[datetime] = Field(default=None)
    corrected_clock_out: Optional[datetime] = Field(default=None)
    reason: str = Field(nullable=False)
    status: str = Field(default="draft", sa_type=correction_status)
    approved_by: Optional[int] = Field(default=None, foreign_key="users.user_id")
    approved_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        {"schema": "public", "constraints": [
            {"name": "correction_required", "check": "corrected_clock_in IS NOT NULL OR corrected_clock_out IS NOT NULL"},
            {"name": "corrected_times_valid", "check": "corrected_clock_out IS NULL OR corrected_clock_in IS NULL OR corrected_clock_out > corrected_clock_in"}
        ]},
    )