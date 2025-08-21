from sqlalchemy import Column, Integer, String, DateTime, Date, DECIMAL, ForeignKey, CheckConstraint, UniqueConstraint, Index, Boolean
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import INET
from app.core.database import Base, ENUM_CLASSES
from app.core.enums import AttendanceStatus

class AttendanceRecords(Base):
    __tablename__ = "attendance_records"
    
    attendance_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    clock_in_time = Column(DateTime(timezone=True), nullable=False)
    clock_out_time = Column(DateTime(timezone=True))
    break_duration = Column(Integer, default=0)
    total_hours = Column(DECIMAL(4, 2))
    overtime_hours = Column(DECIMAL(4, 2), default=0)
    date = Column(Date, nullable=False, server_default=func.current_date())
    status = Column(ENUM_CLASSES['attendance_status'], default=AttendanceStatus.PRESENT, nullable=False)
    ip_address = Column(INET)
    location = Column(String(255))
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        CheckConstraint("clock_out_time IS NULL OR clock_out_time > clock_in_time", name="clock_times_valid"),
        CheckConstraint("break_duration >= 0", name="break_duration_valid"),
        CheckConstraint("total_hours IS NULL OR total_hours >= 0", name="total_hours_valid"),
        CheckConstraint("overtime_hours >= 0", name="overtime_hours_valid"),
        UniqueConstraint('user_id', 'date', name='unique_user_date'),
        Index('idx_attendance_user_clock_in', 'user_id', 'clock_in_time'),
    )