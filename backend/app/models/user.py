from typing import Optional
from sqlmodel import SQLModel, Field, text
from datetime import datetime, date, timezone
from sqlalchemy.sql import func

class User(SQLModel, table=True):
    user_id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: str = Field(
        default_factory=text("'EMP' || LPAD(nextval('employee_id_seq')::text, 6, '0')"),
        unique=True,
        nullable=False
    )
    email: str = Field(unique=True, nullable=False, sa_column_kwargs={"check": "email ~ '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$'"})
    password_hash: str = Field(nullable=False)
    first_name: str = Field(nullable=False)
    last_name: str = Field(nullable=False)
    phone: Optional[str] = Field(
        default=None,
        sa_column_kwargs={"check": "phone IS NULL OR phone ~ '^[\+]?[0-9\s\-\(\)]+$'"}
    )
    hire_date: date = Field(nullable=False, sa_column_kwargs={"check": "hire_date <= CURRENT_DATE"})
    employee_type: str = Field(default="full_time")
    salary: Optional[float] = Field(default=None, ge=0, sa_column_kwargs={"check": "salary IS NULL OR salary >= 0"})
    manager_id: Optional[int] = Field(default=None, foreign_key="users.user_id")
    is_active: bool = Field(default=True)
    deleted_at: Optional[datetime] = Field(default=None, sa_column_kwargs={"check": "deleted_at IS NULL OR is_active = FALSE"})
    last_login: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"server_default": func.current_timestamp(), "onupdate": func.current_timestamp()}
    )

    class Config:
        arbitrary_types_allowed = True