from typing import Optional
from sqlmodel import SQLModel, Field, text
from datetime import datetime, date, timezone
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.sql.schema import CheckConstraint

# Define the employee_type enum for PostgreSQL
employee_type = ENUM(
    'full_time', 'part_time', 'contract', 'intern', 'temporary',
    name='employee_type',
    create_type=True
)

class User(SQLModel, table=True):
    user_id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: Optional[str] = Field(
        default=None,
        unique=True,
        nullable=False,
        sa_column_kwargs={"server_default": text("'EMP' || LPAD(nextval('employee_id_seq')::TEXT, 6, '0')")}
    )
    email: str = Field(unique=True, nullable=False)
    password_hash: str = Field(nullable=False)
    first_name: str = Field(nullable=False)
    last_name: str = Field(nullable=False)
    phone: Optional[str] = Field(default=None)
    hire_date: date = Field(nullable=False)
    employee_type: str = Field(default="full_time", sa_type=employee_type, nullable=False)
    salary: Optional[float] = Field(default=None, ge=0)
    manager_id: Optional[int] = Field(default=None, foreign_key="users.user_id", nullable=True)
    is_active: bool = Field(default=True)
    deleted_at: Optional[datetime] = Field(default=None)
    last_login: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = Field(
        sa_column_kwargs={"server_default": func.current_timestamp(), "onupdate": func.current_timestamp()}
    )

    __table_args__ = (
        CheckConstraint("email ~ '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$'", name="email_format"),
        CheckConstraint("phone IS NULL OR phone ~ '^[\+]?[0-9\s\-\(\)]+$'", name="phone_format"),
        CheckConstraint("hire_date <= CURRENT_DATE", name="hire_date_valid"),
        CheckConstraint("salary IS NULL OR salary >= 0", name="salary_valid"),
        CheckConstraint("deleted_at IS NULL OR is_active = FALSE", name="soft_delete_check"),
    )

    class Config:
        arbitrary_types_allowed = True