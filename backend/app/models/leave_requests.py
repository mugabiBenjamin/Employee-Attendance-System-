from sqlalchemy import Boolean, Column, Integer, String, DateTime, Date, Text, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from app.core.database import Base, ENUM_CLASSES

class LeaveRequests(Base):
    __tablename__ = "leave_requests"
    
    leave_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    leave_type = Column(ENUM_CLASSES['leave_type_enum'], nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    days_requested = Column(Integer, nullable=False)
    reason = Column(Text)
    status = Column(ENUM_CLASSES['leave_request_status_enum'], default='draft')
    approved_by = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    approved_at = Column(DateTime(timezone=True))
    comments = Column(Text)
    attachment_url = Column(String(500))
    is_active = Column(Boolean, default=True)  # Added
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # Added
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="leave_dates_valid"),
        CheckConstraint("days_requested > 0", name="days_requested_valid"),
    )