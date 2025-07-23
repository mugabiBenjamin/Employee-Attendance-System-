from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.sql.schema import CheckConstraint, UniqueConstraint

class Roles(SQLModel, table=True):
    role_id: Optional[int] = Field(default=None, primary_key=True)
    role_name: str = Field(unique=True, nullable=False)
    description: Optional[str] = Field(default=None)
    permissions: dict = Field(default_factory=dict, sa_type=JSONB)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = Field(
        sa_column_kwargs={"server_default": func.current_timestamp(), "onupdate": func.current_timestamp()}
    )
    
    __table_args__ = (
        CheckConstraint("role_name IN ('Employee', 'Manager', 'HR', 'Admin', 'Super_Admin')", name="valid_role_name"),
    )

class UserRoles(SQLModel, table=True):
    user_role_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", nullable=False)
    role_id: int = Field(foreign_key="roles.role_id", nullable=False)
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    assigned_by: Optional[int] = Field(default=None, foreign_key="users.user_id", nullable=True)
    is_active: bool = Field(default=True)
    
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="unique_user_role"),
    )