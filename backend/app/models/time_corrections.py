from sqlalchemy import Boolean, Column, Integer, DateTime, Text, ForeignKey, CheckConstraint, Index
from sqlalchemy.sql import func
from app.core.database import Base, ENUM_CLASSES
from app.core.enums import CorrectionStatus

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
    status = Column(ENUM_CLASSES["correction_status"], default=CorrectionStatus.DRAFT, nullable=False)
    approved_by = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    approved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    is_active = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True))
    
    __table_args__ = (
        CheckConstraint("corrected_clock_in IS NOT NULL OR corrected_clock_out IS NOT NULL", name="correction_required"),
        CheckConstraint("corrected_clock_out IS NULL OR corrected_clock_in IS NULL OR corrected_clock_out > corrected_clock_in", name="corrected_times_valid"),
        CheckConstraint("deleted_at IS NULL OR is_active = FALSE", name="soft_delete_check"),
        Index('idx_time_corrections_attendance_id', 'attendance_id'),
        Index('idx_time_corrections_user_id', 'user_id'),
        Index('idx_time_corrections_approved_by', 'approved_by'),
    )