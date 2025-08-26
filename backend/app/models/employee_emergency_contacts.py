from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, CheckConstraint, Index
from sqlalchemy.sql import func
from app.core.database import Base

class EmployeeEmergencyContacts(Base):
    __tablename__ = "employee_emergency_contacts"
    
    contact_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    contact_name = Column(String(255), nullable=False)
    relationship = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    alternate_phone = Column(String(20))
    email = Column(String(255))
    address = Column(Text)
    is_primary = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    __table_args__ = (
        CheckConstraint("phone ~ '^[\\+]?[0-9\\s\\-\\(\\)]{7,20}$'", name="phone_format"),
        CheckConstraint("alternate_phone IS NULL OR alternate_phone ~ '^[\\+]?[0-9\\s\\-\\(\\)]{7,20}$'", name="alternate_phone_format"),
        CheckConstraint("email IS NULL OR email ~ '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$'", name="email_format"),
        CheckConstraint("deleted_at IS NULL OR is_active = FALSE", name="soft_delete_check"),
        Index('idx_employee_emergency_contacts_user_id', 'user_id'),
    )