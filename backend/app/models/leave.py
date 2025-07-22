from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, date, timezone
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.sql import func

# Define the leave_type and leave_request_status enums for PostgreSQL
leave_type = ENUM(
    'annual', 'sick', 'maternity', 'paternity', 'emergency', 'unpaid', 'casual',
    'compensatory', 'bereavement', 'leave_of_absence', 'public_holiday',
    name='leave_type',
    create_type=True
)

leave_request_status = ENUM(
    'draft', 'under_review', 'approved', 'rejected', 'cancelled', 'completed',
    name='leave_request_status',
    create_type=True
)

class LeaveRequest(SQLModel, table=True):
    leave_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", nullable=False)
    leave_type: str = Field(sa_type=leave_type, nullable=False)
    start_date: date = Field(nullable=False)
    end_date: date = Field(nullable=False)
    days_requested: int = Field(nullable=False, gt=0, sa_column_kwargs={"check": "days_requested > 0"})
    reason: Optional[str] = Field(default=None)
    status: str = Field(default="draft", sa_type=leave_request_status)
    approved_by: Optional[int] = Field(default=None, foreign_key="users.user_id")
    approved_at: Optional[datetime] = Field(default=None)
    comments: Optional[str] = Field(default=None)
    attachment_url: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"server_default": func.current_timestamp(), "onupdate": func.current_timestamp()}
    )
    __table_args__ = (
        {"schema": "public", "constraints": [
            {"name": "leave_dates_valid", "check": "end_date >= start_date"}
        ]},
    )

class LeaveBalance(SQLModel, table=True):
    balance_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", nullable=False)
    leave_type: str = Field(sa_type=leave_type, nullable=False)
    allocated_days: int = Field(default=0, ge=0, sa_column_kwargs={"check": "allocated_days >= 0"})
    used_days: int = Field(default=0, ge=0, sa_column_kwargs={"check": "used_days >= 0"})
    carried_forward: int = Field(default=0, ge=0, sa_column_kwargs={"check": "carried_forward >= 0"})
    year: int = Field(
        default_factory=lambda: datetime.now().year,
        sa_column_kwargs={"check": "year >= 2020 AND year <= 2050"}
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"server_default": func.current_timestamp(), "onupdate": func.current_timestamp()}
    )
    __table_args__ = (
        {"schema": "public", "constraints": [
            {"name": "unique_user_leave_type_year", "unique": ["user_id", "leave_type", "year"]}
        ]},
    )