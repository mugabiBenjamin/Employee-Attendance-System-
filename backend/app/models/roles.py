from sqlalchemy import Column, Integer, String, DateTime, Text, CheckConstraint, Boolean
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base

class Roles(Base):
    __tablename__ = "roles"
    
    role_id = Column(Integer, primary_key=True)
    role_name = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    permissions = Column(JSONB, default={})
    is_active = Column(Boolean, default=True) 
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    deleted_at = Column(DateTime(timezone=True), nullable=True)  
    
    __table_args__ = (
        CheckConstraint("role_name IN ('Employee', 'Manager', 'HR', 'Admin', 'Super_Admin')", name="role_name_valid"),
    )