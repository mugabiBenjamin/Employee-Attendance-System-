from sqlalchemy import CheckConstraint, Column, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
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
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship(
        "Users",
        back_populates="user_roles",
        foreign_keys=[user_id],
        overlaps="user_roles",
        lazy="selectin"
    )
    role = relationship(
        "Roles",
        back_populates="user_roles",
        foreign_keys=[role_id],
        overlaps="user_roles",
        lazy="selectin"
    )
    assigned_by_user = relationship(
        "Users",
        foreign_keys=[assigned_by],
        overlaps="user_roles",
        lazy="selectin"
    )
    
    __table_args__ = (
        UniqueConstraint('user_id', 'role_id', name='unique_user_role'),
        CheckConstraint("deleted_at IS NULL OR is_active = FALSE", name="soft_delete_check"),
        Index('idx_user_roles_assigned_by', 'assigned_by'),
    )