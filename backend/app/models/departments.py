from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, DECIMAL, ForeignKey, CheckConstraint, Index
from sqlalchemy.sql import func
from app.core.database import Base

class Departments(Base):
    __tablename__ = "departments"
    
    department_id = Column(Integer, primary_key=True)
    department_name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    manager_id = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    budget = Column(DECIMAL(15, 2))
    location = Column(String(255))
    is_active = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    __table_args__ = (
        CheckConstraint("budget IS NULL OR budget >= 0", name="budget_valid"),
        CheckConstraint("deleted_at IS NULL OR is_active = FALSE", name="soft_delete_check"),
        CheckConstraint("department_name != ''", name="department_name_not_empty"),
        Index('idx_departments_manager_id', 'manager_id'),
    )