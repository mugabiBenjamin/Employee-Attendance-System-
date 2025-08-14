from sqlalchemy import Column, Integer, DateTime, Text, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base
from app.core.db_enums import leave_request_status_enum

class LeaveApprovalWorkflow(Base):
    __tablename__ = "leave_approval_workflow"
    
    workflow_id = Column(Integer, primary_key=True)
    leave_id = Column(Integer, ForeignKey('leave_requests.leave_id', ondelete='CASCADE'), nullable=False)
    approver_id = Column(Integer, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    level = Column(Integer, nullable=False)
    status = Column(leave_request_status_enum, default='under_review')
    comments = Column(Text)
    action_taken_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    
    __table_args__ = (
        CheckConstraint("level >= 1 AND level <= 5", name="level_valid"),
        UniqueConstraint('leave_id', 'approver_id', 'level', name='unique_leave_approver_level'),
    )