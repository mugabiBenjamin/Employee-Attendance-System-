from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone

class User(SQLModel, table=True):
    user_id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: str = Field(unique=True, nullable=False)
    email: str = Field(unique=True, nullable=False, regex=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    password_hash: str = Field(nullable=False)
    first_name: str = Field(nullable=False)
    last_name: str = Field(nullable=False)
    phone: Optional[str] = Field(default=None, regex=r'^[\+]?[0-9\s\-\(\)]+$')
    hire_date: datetime = Field(nullable=False)
    employee_type: str = Field(default="full_time")
    salary: Optional[float] = Field(default=None, ge=0)
    manager_id: Optional[int] = Field(default=None, foreign_key="users.user_id")
    is_active: bool = Field(default=True)
    deleted_at: Optional[datetime] = Field(default=None)
    last_login: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=datetime.now(timezone.utc))