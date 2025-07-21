from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, date, timezone

class LeaveRequest(SQLModel, table=True):
    leave_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.user_id", nullable=False)
    leave_type: str = Field(nullable=False)
    start_date: date = Field(nullable=False)
    end_date: date = Field(nullable=False)
    days_requested: int = Field(nullable=False, gt=0)
    reason: Optional[str] = Field(default=None)
    status: str = Field(default="draft")
    approved_by: Optional[int] = Field(default=None, foreign_key="user.user_id")
    approved_at: Optional[datetime] = Field(default=None)
    comments: Optional[str] = Field(default=None)
    attachment_url: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=datetime.now(timezone.utc))

class LeaveBalance(SQLModel, table=True):
    balance_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.user_id", nullable=False)
    leave_type: str = Field(nullable=False)
    allocated_days: int = Field(default=0, ge=0)
    used_days: int = Field(default=0, ge=0)
    carried_forward: int = Field(default=0, ge=0)
    year: int = Field(default_factory=lambda: datetime.now().year)
    updated_at: datetime = Field(default_factory=datetime.now(timezone.utc))