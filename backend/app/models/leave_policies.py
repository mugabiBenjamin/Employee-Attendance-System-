from sqlalchemy import Column, Integer, Boolean, DateTime, Date, DECIMAL, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.sql import func
from app.core.database import Base, ENUM_CLASSES

class LeavePolicies(Base):
    __tablename__ = "leave_policies"
    
    policy_id = Column(Integer, primary_key=True)
    employee_type = Column(ENUM_CLASSES['employee_type'], nullable=False)
    leave_type = Column(ENUM_CLASSES['leave_type'], nullable=False)
    annual_allocation = Column(Integer, nullable=False, default=0)
    carry_forward_limit = Column(Integer, default=0)
    max_consecutive_days = Column(Integer)
    requires_approval = Column(Boolean, default=True)
    approval_levels = Column(Integer, default=1)
    accrual_rate = Column(DECIMAL(10, 2), default=0)  # days per month
    effective_from = Column(Date, nullable=False, server_default=func.current_date())
    effective_to = Column(Date)
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    __table_args__ = (
        CheckConstraint("annual_allocation >= 0", name="allocation_valid"),
        CheckConstraint("carry_forward_limit >= 0", name="carry_forward_valid"),
        CheckConstraint("max_consecutive_days IS NULL OR max_consecutive_days > 0", name="max_days_valid"),
        CheckConstraint("approval_levels >= 1 AND approval_levels <= 5", name="approval_levels_valid"),
        CheckConstraint("accrual_rate >= 0", name="accrual_rate_valid"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="policy_dates_valid"),
        CheckConstraint("version >= 1", name="version_valid"),
        CheckConstraint("deleted_at IS NULL OR is_active = FALSE", name="soft_delete_check"),
        UniqueConstraint('employee_type', 'leave_type', 'effective_from', name='unique_policy_type'),
        Index('idx_leave_policies_employee_type', 'employee_type'),
        Index('idx_leave_policies_leave_type', 'leave_type'),
        Index('idx_leave_policies_effective_from', 'effective_from'),
    )