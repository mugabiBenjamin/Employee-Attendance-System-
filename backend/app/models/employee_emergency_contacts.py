from typing import Optional
from sqlalchemy import CheckConstraint
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from sqlalchemy.sql import func

class EmployeeEmergencyContact(SQLModel, table=True):
    contact_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", nullable=False)
    contact_name: str = Field(nullable=False)
    relationship: str = Field(nullable=False)
    phone: str = Field(nullable=False)
    email: Optional[str] = Field(default=None)
    address: Optional[str] = Field(default=None)
    is_primary: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = Field(
        sa_column_kwargs={"server_default": func.current_timestamp(), "onupdate": func.current_timestamp()}
    )
    
    __table_args__ = (
        CheckConstraint("phone ~ '^[\+]?[0-9\s\-\(\)]+$'", name="phone_format"),
        CheckConstraint("email IS NULL OR email ~ '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$'", name="email_format"),
    )