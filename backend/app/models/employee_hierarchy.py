from sqlalchemy import Boolean, Column, Integer, DateTime, Date, ForeignKey, CheckConstraint, Index
from sqlalchemy.sql import func
from app.core.database import Base

class EmployeeHierarchy(Base):
    __tablename__ = "employee_hierarchy"
    
    hierarchy_id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    manager_id = Column(Integer, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    level = Column(Integer, nullable=False, default=1)
    effective_from = Column(Date, nullable=False, server_default=func.current_date())
    effective_to = Column(Date)
    is_active = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    __table_args__ = (
        CheckConstraint("level >= 1 AND level <= 10", name="level_valid"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="hierarchy_dates_valid"),
        CheckConstraint("employee_id != manager_id", name="no_self_reporting"),
        CheckConstraint("effective_from <= current_date", name="effective_from_valid"),
        CheckConstraint("deleted_at IS NULL OR is_active = FALSE", name="soft_delete_check"),
        Index('idx_employee_hierarchy_employee_id', 'employee_id'),
        Index('idx_employee_hierarchy_manager_id', 'manager_id'),
    )