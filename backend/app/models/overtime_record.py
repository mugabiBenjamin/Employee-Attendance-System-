from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone

class OvertimeRecord(SQLModel, table=True):
    overtime_id: Optional[int] = Field(default=None, primary_key=True)
    attendance_id: int = Field(foreign_key="attendance_records.attendance_id", nullable=False)
    user_id: int = Field(foreign_key="users.user_id", nullable=False)
    overtime_hours: float = Field(nullable=False, sa_column_kwargs={"check": "overtime_hours > 0"})
    overtime_rate: float = Field(default=1.5, sa_column_kwargs={"check": "overtime_rate > 0"})
    overtime_amount: Optional[float] = Field(default=None)
    approved_by: Optional[int] = Field(default=None, foreign_key="users.user_id")
    approved_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))