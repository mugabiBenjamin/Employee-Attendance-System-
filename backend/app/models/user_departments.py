from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint, Index, CheckConstraint
from sqlalchemy.sql import func
from app.core.database import Base

class UserDepartments(Base):
    __tablename__ = "user_departments"
    
    user_department_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    department_id = Column(Integer, ForeignKey('departments.department_id', ondelete='CASCADE'), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    assigned_by = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    is_primary = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    __table_args__ = (
        UniqueConstraint('user_id', 'department_id', name='unique_user_department'),
        CheckConstraint("deleted_at IS NULL OR is_active = FALSE", name="soft_delete_check"),
        Index('idx_user_departments_user_id', 'user_id'),
        Index('idx_user_departments_department_id', 'department_id'),
        Index('idx_user_departments_assigned_by', 'assigned_by'),
    )