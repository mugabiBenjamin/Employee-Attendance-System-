from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, time, timezone
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy import CheckConstraint

# Define the shift_type enum for PostgreSQL
shift_type = ENUM(
    'morning', 'afternoon', 'night', 'flexible', 'split',
    name='shift_type',
    create_type=True
)

class ShiftPattern(SQLModel, table=True):
    pattern_id: Optional[int] = Field(default=None, primary_key=True)
    pattern_name: str = Field(nullable=False)
    shift_type: str = Field(sa_type=shift_type, nullable=False)
    start_time: time = Field(nullable=False)
    end_time: time = Field(nullable=False)
    break_duration: int = Field(default=0)
    is_overnight: bool = Field(default=False)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        CheckConstraint("break_duration >= 0", name="check_break_duration"),
    )