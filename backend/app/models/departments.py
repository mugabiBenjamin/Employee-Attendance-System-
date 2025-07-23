from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from sqlalchemy.sql import func
from sqlalchemy.sql.schema import CheckConstraint

class Departments(SQLModel, table=True):
    department_id: Optional[int] = Field(default=None, primary_key=True)
    department_name: str = Field(unique=True, nullable=False)
    description: Optional[str] = Field(default=None)
    manager_id: Optional[int] = Field(default=None, foreign_key="users.user_id", nullable=True)
    budget: Optional[float] = Field(default=None)
    location: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True)
    deleted_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = Field(
        sa_column_kwargs={"server_default": func.current_timestamp(), "onupdate": func.current_timestamp()}
    )
    
    __table_args__ = (
        CheckConstraint("budget IS NULL OR budget >= 0", name="budget_non_negative"),
        CheckConstraint("deleted_at IS NULL OR is_active = FALSE", name="soft_delete_check"),
    )