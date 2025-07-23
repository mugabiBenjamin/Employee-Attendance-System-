from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, date, timezone
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.sql import func
from sqlalchemy import UniqueConstraint

# Define the employee_type and leave_type enums for PostgreSQL
employee_type = ENUM(
    'full_time', 'part_time', 'contract', 'intern', 'temporary',
    name='employee_type',
    create_type=True
)

leave_type = ENUM(
    'annual', 'sick', 'maternity', 'paternity', 'emergency', 'unpaid', 'casual',
    'compensatory', 'bereavement', 'leave_of_absence', 'public_holiday',
    name='leave_type',
    create_type=True
)

class LeavePolicy(SQLModel, table=True):
    policy_id: Optional[int] = Field(default=None, primary_key=True)
    employee_type: str = Field(sa_type=employee_type, nullable=False)
    leave_type: str = Field(sa_type=leave_type, nullable=False)
    annual_allocation: int = Field(default=0, sa_column_kwargs={"check": "annual_allocation >= 0"})
    carry_forward_limit: int = Field(default=0, sa_column_kwargs={"check": "carry_forward_limit >= 0"})
    max_consecutive_days: Optional[int] = Field(default=None, sa_column_kwargs={"check": "max_consecutive_days IS NULL OR max_consecutive_days > 0"})
    requires_approval: bool = Field(default=True)
    approval_levels: int = Field(default=1, sa_column_kwargs={"check": "approval_levels >= 1 AND approval_levels <= 5"})
    accrual_rate: float = Field(default=0, sa_column_kwargs={"check": "accrual_rate >= 0"})
    effective_from: date = Field(default_factory=date.today)
    effective_to: Optional[date] = Field(default=None, sa_column_kwargs={"check": "effective_to IS NULL OR effective_to >= effective_from"})
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = Field(
        sa_column_kwargs={"server_default": func.current_timestamp(), "onupdate": func.current_timestamp()}
    )
    
    __table_args__ = (
        UniqueConstraint("employee_type", "leave_type", "effective_from", name="unique_policy_type"),
    )