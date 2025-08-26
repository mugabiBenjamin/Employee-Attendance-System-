from sqlalchemy import Column, Integer, String, Boolean, DateTime, Time, CheckConstraint, Index
from sqlalchemy.sql import func
from app.core.database import Base, ENUM_CLASSES

class ShiftPatterns(Base):
    __tablename__ = "shift_patterns"
    
    pattern_id = Column(Integer, primary_key=True)
    pattern_name = Column(String(100), nullable=False)
    shift_type = Column(ENUM_CLASSES['shift_type'], nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    break_duration = Column(Integer, default=0)  # minutes
    is_overnight = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    __table_args__ = (
        CheckConstraint("break_duration >= 0", name="break_duration_valid"),
        CheckConstraint("is_overnight = TRUE OR start_time < end_time", name="shift_time_valid"),
        CheckConstraint("deleted_at IS NULL OR is_active = FALSE", name="soft_delete_check"),
        Index('idx_shift_patterns_name', 'pattern_name'),
    )