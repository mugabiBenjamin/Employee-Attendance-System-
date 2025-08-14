from sqlalchemy import Column, Integer, String, Boolean, DateTime, CheckConstraint, Time
from sqlalchemy.sql import func
from app.core.database import Base
from app.core.db_enums import shift_type_enum

class ShiftPatterns(Base):
    __tablename__ = "shift_patterns"
    
    pattern_id = Column(Integer, primary_key=True)
    pattern_name = Column(String(100), nullable=False)
    shift_type = Column(shift_type_enum, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    break_duration = Column(Integer, default=0)  # minutes
    is_overnight = Column(Boolean, default=False)  # for night shifts crossing midnight
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    
    __table_args__ = (
        CheckConstraint("break_duration >= 0", name="break_duration_valid"),
    )