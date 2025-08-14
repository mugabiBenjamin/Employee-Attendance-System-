from sqlalchemy import Column, Integer, Boolean, DateTime, Date, DECIMAL, CheckConstraint, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base
from app.core.db_enums import employee_type_enum, leave_type_enum

class LeavePolicies(Base):
    __tablename__ = "leave_policies"
    
    policy_id = Column(Integer, primary_key=True)
    employee_type = Column(employee_type_enum, nullable=False)
    leave_type = Column(leave_type_enum, nullable=False)
    annual_allocation = Column(Integer, nullable=False, default=0)
    carry_forward_limit = Column(Integer, default=0)
    max_consecutive_days = Column(Integer)
    requires_approval = Column(Boolean, default=True)
    approval_levels = Column(Integer, default=1)
    accrual_rate = Column(DECIMAL(4, 2), default=0)  # days per month
    effective_from = Column(Date, nullable=False, server_default=func.current_date())
    effective_to = Column(Date)
    is_active = Column(Boolean, default=True)  # Added
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # Added
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    __table_args__ = (
        CheckConstraint("annual_allocation >= 0", name="allocation_valid"),
        CheckConstraint("carry_forward_limit >= 0", name="carry_forward_valid"),
        CheckConstraint("max_consecutive_days IS NULL OR max_consecutive_days > 0", name="max_days_valid"),
        CheckConstraint("approval_levels >= 1 AND approval_levels <= 5", name="approval_levels_valid"),
        CheckConstraint("accrual_rate >= 0", name="accrual_rate_valid"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="policy_dates_valid"),
        UniqueConstraint('employee_type', 'leave_type', 'effective_from', name='unique_policy_type'),
    )