from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func

class UserDepartments(Base):
    __tablename__ = "user_departments"
    
    user_department_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    department_id = Column(Integer, ForeignKey('departments.department_id', ondelete='CASCADE'), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    is_primary = Column(Boolean, default=False)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'department_id', name='unique_user_department'),
    )