from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, date, timezone

class HolidayCalendar(SQLModel, table=True):
    holiday_id: Optional[int] = Field(default=None, primary_key=True)
    holiday_name: str = Field(nullable=False)
    holiday_date: date = Field(nullable=False)
    is_recurring: bool = Field(default=False)
    applies_to_all: bool = Field(default=True)
    department_id: Optional[int] = Field(default=None, foreign_key="departments.department_id")
    year: int = Field(
        default_factory=lambda: datetime.now().year,
        sa_column_kwargs={"check": "year >= 2020 AND year <= 2050"}
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        {"schema": "public", "constraints": [
            {"name": "unique_holiday_date", "unique": ["holiday_date", "department_id"]}
        ]},
    )