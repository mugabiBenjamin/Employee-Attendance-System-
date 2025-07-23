from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import ENUM, JSONB, INET
from sqlalchemy.sql import func

# Define the system_action enum for PostgreSQL
system_action = ENUM(
    'INSERT', 'UPDATE', 'DELETE', 'LOGIN', 'LOGOUT', 'CLOCK_IN', 'CLOCK_OUT',
    'password_change', 'profile_update', 'data_export', 'data_import',
    'assign_role', 'revoke_role', 'view_report', 'approve_leave', 'reject_leave',
    'create_department', 'delete_department',
    name='system_action',
    create_type=True
)

class SystemLog(SQLModel, table=True):
    log_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.user_id")
    action: str = Field(sa_type=system_action, nullable=False)
    table_affected: Optional[str] = Field(default=None)
    record_id: Optional[int] = Field(default=None)
    old_values: Optional[dict] = Field(default=None, sa_type=JSONB)
    new_values: Optional[dict] = Field(default=None, sa_type=JSONB)
    ip_address: Optional[str] = Field(default=None, sa_type=INET)
    user_agent: Optional[str] = Field(default=None)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"server_default": func.current_timestamp()}
    )