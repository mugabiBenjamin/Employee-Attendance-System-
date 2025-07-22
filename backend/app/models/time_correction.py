from typing import Optional
from sqlmodel import SQLModel, Field, Enum
from datetime import datetime, timezone
import enum

class CorrectionStatus(str, enum.Enum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    COMPLETED = "completed"

class TimeCorrectionBase(SQLModel):
    attendance_id: int = Field(foreign_key="attendance_records.attendance_id", index=True)
    user_id: int = Field(foreign_key="users.user_id", index=True)
    original_clock_in: Optional[datetime] = Field(default=None)
    original_clock_out: Optional[datetime] = Field(default=None)
    corrected_clock_in: Optional[datetime] = Field(default=None)
    corrected_clock_out: Optional[datetime] = Field(default=None)
    reason: str
    status: CorrectionStatus = Field(default=CorrectionStatus.DRAFT, sa_type=Enum(CorrectionStatus))
    approved_by: Optional[int] = Field(default=None, foreign_key="users.user_id")
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
    status: Optional[CorrectionStatus] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None

class TimeCorrectionOut(TimeCorrectionBase):
    correction_id: int
    created_at: datetime