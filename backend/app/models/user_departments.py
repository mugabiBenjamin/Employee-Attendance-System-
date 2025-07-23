from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from sqlalchemy import UniqueConstraint

class UserDepartment(SQLModel, table=True):
    user_department_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", nullable=False)
    department_id: int = Field(foreign_key="departments.department_id", nullable=False)
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_primary: bool = Field(default=False)
    
    __table_args__ = (
        UniqueConstraint("user_id", "department_id", name="unique_user_department"),
    )