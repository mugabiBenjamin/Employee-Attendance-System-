from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone

class Role(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    role_name: str = Field(unique=True, nullable=False)
    description: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserRoles(SQLModel, table=True):
    user_id: int = Field(foreign_key="users.user_id", primary_key=True)
    role_id: int = Field(foreign_key="roles.id", primary_key=True)
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))