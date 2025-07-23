from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from sqlalchemy.sql import func

class EmployeeEmergencyContact(SQLModel, table=True):
    contact_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", nullable=False)
    contact_name: str = Field(nullable=False)
    relationship: str = Field(nullable=False)
    phone: str = Field(nullable=False, sa_column_kwargs={"check": "phone ~ '^[\+]?[0-9\s\-\(\)]+$'"})
    email: Optional[str] = Field(default=None, sa_column_kwargs={"check": "email IS NULL OR email ~ '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$'"})
    address: Optional[str] = Field(default=None)
    is_primary: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = Field(
        sa_column_kwargs={"server_default": func.current_timestamp(), "onupdate": func.current_timestamp()}
    )