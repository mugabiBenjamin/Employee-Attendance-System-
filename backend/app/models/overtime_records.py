from sqlalchemy import Column, Integer, DateTime, DECIMAL, ForeignKey, CheckConstraint
from sqlalchemy.sql import func

class OvertimeRecords(Base):
    __tablename__ = "overtime_records"
    
    overtime_id = Column(Integer, primary_key=True)
    attendance_id = Column(Integer, ForeignKey('attendance_records.attendance_id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    overtime_hours = Column(DECIMAL(4, 2), nullable=False)
    overtime_rate = Column(DECIMAL(4, 2), default=1.5)
    overtime_amount = Column(DECIMAL(10, 2))
    approved_by = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    approved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    
    __table_args__ = (
        CheckConstraint("overtime_hours > 0", name="overtime_hours_valid"),
        CheckConstraint("overtime_rate > 0", name="overtime_rate_valid"),
    )