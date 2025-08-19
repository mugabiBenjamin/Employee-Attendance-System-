from sqlalchemy import Boolean, Column, Integer, DateTime, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base, ENUM_CLASSES

class LeaveBalances(Base):
    __tablename__ = "leave_balances"
    
    balance_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    leave_type = Column(ENUM_CLASSES['leave_type_enum'], nullable=False)
    allocated_days = Column(Integer, nullable=False, default=0)
    used_days = Column(Integer, nullable=False, default=0)
    carried_forward = Column(Integer, nullable=False, default=0)
    year = Column(Integer, nullable=False, server_default=func.extract('year', func.current_date()))
    is_active = Column(Boolean, default=True)  # Added
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # Added
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    __table_args__ = (
        CheckConstraint("allocated_days >= 0", name="allocated_days_valid"),
        CheckConstraint("used_days >= 0", name="used_days_valid"),
        CheckConstraint("carried_forward >= 0", name="carried_forward_valid"),
        CheckConstraint("year >= 2020 AND year <= 2050", name="year_valid"),
        UniqueConstraint('user_id', 'leave_type', 'year', name='unique_user_leave_type_year'),
    )