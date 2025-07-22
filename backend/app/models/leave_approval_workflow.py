from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import ENUM

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
    level: int = Field(nullable=False, sa_column_kwargs={"check": "level >= 1 AND level <= 5"})
    status: str = Field(default="under_review", sa_type=leave_request_status)
    comments: Optional[str] = Field(default=None)
    action_taken_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        {"schema": "public", "constraints": [
            {"name": "unique_leave_approver_level", "unique": ["leave_id", "approver_id", "level"]}
        ]},
    )