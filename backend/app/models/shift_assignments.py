from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import date, datetime, timezone

class ShiftAssignment(SQLModel, table=True):
    __tablename__ = "shift_assignments"

    assignment_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", index=True)
    pattern_id: int = Field(foreign_key="shift_patterns.pattern_id", index=True)
    effective_from: date = Field(index=True)
    effective_to: Optional[date] = Field(default=None)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))