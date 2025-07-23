from typing import Optional
from sqlalchemy import CheckConstraint
from sqlmodel import SQLModel, Field
from datetime import datetime, date as dt, timezone

class EmployeeHierarchy(SQLModel, table=True):
    hierarchy_id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: int = Field(foreign_key="users.user_id", nullable=False)
    manager_id: int = Field(foreign_key="users.user_id", nullable=False)
    level: int = Field(default=1)
    effective_from: dt = Field(default_factory=dt.today)
    effective_to: Optional[dt] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        CheckConstraint("level >= 1 AND level <= 10", name="level_range"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="date_range_valid"),
        CheckConstraint("employee_id != manager_id", name="no_self_reporting"),
    )