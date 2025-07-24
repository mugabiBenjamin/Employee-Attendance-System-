from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, date, timezone
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.sql import func
from sqlalchemy.sql.schema import CheckConstraint, UniqueConstraint

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

class LeaveRequests(SQLModel, table=True):
    leave_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", nullable=False)
    leave_type: str = Field(sa_type=leave_type, nullable=False)
    start_date: date = Field(nullable=False)
    end_date: date = Field(nullable=False)
    days_requested: int = Field(nullable=False, gt=0)
    reason: Optional[str] = Field(default=None)
    status: str = Field(default="draft", sa_type=leave_request_status)
    approved_by: Optional[int] = Field(default=None, foreign_key="users.user_id", nullable=True)
    approved_at: Optional[datetime] = Field(default=None)
    comments: Optional[str] = Field(default=None)
    attachment_url: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = Field(
        sa_column_kwargs={"server_default": func.current_timestamp(), "onupdate": func.current_timestamp()}
    )
    
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="leave_dates_valid"),
        CheckConstraint("days_requested > 0", name="days_requested_positive"),
    )

class LeaveBalance(SQLModel, table=True):
    balance_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", nullable=False)
    leave_type: str = Field(sa_type=leave_type, nullable=False)
    allocated_days: int = Field(default=0, ge=0)
    used_days: int = Field(default=0, ge=0)
    carried_forward: int = Field(default=0, ge=0)
    year: int = Field(default_factory=lambda: datetime.now().year)
    updated_at: Optional[datetime] = Field(
        sa_column_kwargs={"server_default": func.current_timestamp(), "onupdate": func.current_timestamp()}
    )
    
    __table_args__ = (
        CheckConstraint("allocated_days >= 0", name="allocated_days_non_negative"),
        CheckConstraint("used_days >= 0", name="used_days_non_negative"),
        CheckConstraint("carried_forward >= 0", name="carried_forward_non_negative"),
        CheckConstraint("year >= 2020 AND year <= 2050", name="year_valid_range"),
        UniqueConstraint("user_id", "leave_type", "year", name="unique_user_leave_type_year"),
    )

class LeavePolicy(SQLModel, table=True):
    policy_id: Optional[int] = Field(default=None, primary_key=True)
    leave_type: str = Field(sa_type=leave_type, nullable=False)
    default_days: int = Field(default=0, ge=0)
    max_carry_forward: int = Field(default=0, ge=0)
    requires_approval: bool = Field(default=True)
    advance_notice_days: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = Field(
        sa_column_kwargs={"server_default": func.current_timestamp(), "onupdate": func.current_timestamp()}
    )
    
    __table_args__ = (
        CheckConstraint("default_days >= 0", name="default_days_non_negative"),
        CheckConstraint("max_carry_forward >= 0", name="max_carry_forward_non_negative"),
        CheckConstraint("advance_notice_days >= 0", name="advance_notice_days_non_negative"),
    )