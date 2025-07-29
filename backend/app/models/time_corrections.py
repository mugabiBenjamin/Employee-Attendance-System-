from sqlalchemy import Column, Integer, DateTime, Text, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import ENUM
from app.core.database import Base

correction_status_enum = ENUM('draft', 'under_review', 'approved', 'rejected', 'cancelled', 'completed', name='correction_status')

class TimeCorrections(Base):
    __tablename__ = "time_corrections"
    
    correction_id = Column(Integer, primary_key=True)
    attendance_id = Column(Integer, ForeignKey('attendance_records.attendance_id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    original_clock_in = Column(DateTime(timezone=True))
    original_clock_out = Column(DateTime(timezone=True))
    corrected_clock_in = Column(DateTime(timezone=True))
    corrected_clock_out = Column(DateTime(timezone=True))
    reason = Column(Text, nullable=False)
    status = Column(correction_status_enum, default='draft')
    approved_by = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    approved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    
    __table_args__ = (
        CheckConstraint("corrected_clock_in IS NOT NULL OR corrected_clock_out IS NOT NULL", name="correction_required"),
        CheckConstraint("corrected_clock_out IS NULL OR corrected_clock_in IS NULL OR corrected_clock_out > corrected_clock_in", name="corrected_times_valid"),
    )