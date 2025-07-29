from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint
from app.core.database import Base
from sqlalchemy.sql import func

class UserRoles(Base):
    __tablename__ = "user_roles"
    
    user_role_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    role_id = Column(Integer, ForeignKey('roles.role_id', ondelete='CASCADE'), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    assigned_by = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    is_active = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'role_id', name='unique_user_role'),
    )