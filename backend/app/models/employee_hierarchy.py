from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, date, timezone

class EmployeeHierarchy(SQLModel, table=True):
    hierarchy_id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: int = Field(foreign_key="users.user_id", nullable=False)
    manager_id: int = Field(foreign_key="users.user_id", nullable=False)
    level: int = Field(default=1, sa_column_kwargs={"check": "level >= 1 AND level <= 10"})
    effective_from: date = Field(default_factory=date.today)
    effective_to: Optional[date] = Field(default=None, sa_column_kwargs={"check": "effective_to IS NULL OR effective_to >= effective_from"})
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        {"schema": "public", "constraints": [
            {"name": "no_self_reporting", "check": "employee_id != manager_id"}
        ]},
    )