from sqlalchemy import Column, Integer, DateTime, Text, CheckConstraint, Boolean
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base, ENUM_CLASSES

class Roles(Base):
    __tablename__ = "roles"
    
    role_id = Column(Integer, primary_key=True)
    role_name = Column(ENUM_CLASSES['role_name'], unique=True, nullable=False)
    description = Column(Text)
    permissions = Column(JSONB, default={})
    is_active = Column(Boolean, default=True) 
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    deleted_at = Column(DateTime(timezone=True), nullable=True)  
    
    __table_args__ = (
        CheckConstraint("permissions::text ~ '^{.*}$'", name="permissions_json_format"),
    )