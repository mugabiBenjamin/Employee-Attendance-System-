from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone

class UserDepartment(SQLModel, table=True):
    user_department_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", nullable=False)
    department_id: int = Field(foreign_key="departments.department_id", nullable=False)
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_primary: bool = Field(default=False)
    __table_args__ = (
        {"schema": "public", "constraints": [
            {"name": "unique_user_department", "unique": ["user_id", "department_id"]}
        ]},
    )