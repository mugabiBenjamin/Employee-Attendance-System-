from sqlalchemy import Boolean, Column, Integer, DateTime, Date, DECIMAL, ForeignKey, CheckConstraint, Index, String
from sqlalchemy.sql import func
from app.core.database import Base, ENUM_CLASSES
from app.core.enums import OvertimeStatus

class OvertimeRecords(Base):
    __tablename__ = "overtime_records"
    
    overtime_id = Column(Integer, primary_key=True)
    attendance_id = Column(Integer, ForeignKey('attendance_records.attendance_id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    date = Column(Date, nullable=False)
    overtime_hours = Column(DECIMAL(4, 2), nullable=False)
    overtime_rate = Column(DECIMAL(4, 2), default=1.5)
    overtime_amount = Column(DECIMAL(10, 2))
    description = Column(String(255))
    status = Column(ENUM_CLASSES["overtime_status"], default=OvertimeStatus.PENDING, nullable=False)
    comments = Column(String(255))
    approved_by = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    approved_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    __table_args__ = (
        CheckConstraint("overtime_hours > 0", name="overtime_hours_valid"),
        CheckConstraint("overtime_rate > 0", name="overtime_rate_valid"),
        CheckConstraint("overtime_amount = overtime_hours * overtime_rate", name="overtime_amount_valid"),
        CheckConstraint("deleted_at IS NULL OR is_active = FALSE", name="soft_delete_check"),
        Index('idx_overtime_records_user_id', 'user_id'),
        Index('idx_overtime_records_attendance_id', 'attendance_id'),
    )