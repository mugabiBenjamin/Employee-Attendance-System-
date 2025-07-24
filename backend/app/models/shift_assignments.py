from sqlalchemy import Column, Integer, Boolean, DateTime, Date, ForeignKey, CheckConstraint
from sqlalchemy.sql import func

class ShiftAssignments(Base):
    __tablename__ = "shift_assignments"
    
    assignment_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    pattern_id = Column(Integer, ForeignKey('shift_patterns.pattern_id', ondelete='CASCADE'), nullable=False)
    effective_from = Column(Date, nullable=False, server_default=func.current_date())
    effective_to = Column(Date)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    __table_args__ = (
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="assignment_dates_valid"),
    )