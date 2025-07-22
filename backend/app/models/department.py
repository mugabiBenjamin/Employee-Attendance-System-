from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from sqlalchemy.sql import func

class Department(SQLModel, table=True):
    department_id: Optional[int] = Field(default=None, primary_key=True)
    department_name: str = Field(unique=True, nullable=False)
    description: Optional[str] = Field(default=None)
    manager_id: Optional[int] = Field(default=None, foreign_key="users.user_id")
    budget: Optional[float] = Field(default=None, sa_column_kwargs={"check": "budget IS NULL OR budget >= 0"})
    location: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True)
    deleted_at: Optional[datetime] = Field(default=None, sa_column_kwargs={"check": "deleted_at IS NULL OR is_active = FALSE"})
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"server_default": func.current_timestamp(), "onupdate": func.current_timestamp()}
    )