from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy import UniqueConstraint, CheckConstraint

# Define the leave_request_status enum for PostgreSQL
leave_request_status = ENUM(
    'draft', 'under_review', 'approved', 'rejected', 'cancelled', 'completed',
    name='leave_request_status',
    create_type=True
)

class LeaveApprovalWorkflow(SQLModel, table=True):
    workflow_id: Optional[int] = Field(default=None, primary_key=True)
    leave_id: int = Field(foreign_key="leave_requests.leave_id", nullable=False)
    approver_id: int = Field(foreign_key="users.user_id", nullable=False)
    level: int = Field(nullable=False)
    status: str = Field(default="under_review", sa_type=leave_request_status)
    comments: Optional[str] = Field(default=None)
    action_taken_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        UniqueConstraint("leave_id", "approver_id", "level", name="unique_leave_approver_level"),
        CheckConstraint("level >= 1 AND level <= 5", name="check_level_range"),
    )