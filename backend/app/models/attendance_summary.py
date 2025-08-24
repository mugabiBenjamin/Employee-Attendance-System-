from sqlalchemy import Column, Integer, String, DateTime, Date, DECIMAL, UniqueConstraint, Boolean, Text
from sqlalchemy.sql import func
from app.core.database import Base, ENUM_CLASSES

class AttendanceSummary(Base):
    __tablename__ = "attendance_summary"
    
    user_id = Column(Integer, primary_key=True)
    employee_id = Column(String(20))
    full_name = Column(Text)
    department_name = Column(String(100))
    attendance_summary_date = Column(Date, primary_key=True)
    status = Column(ENUM_CLASSES['attendance_status'])
    total_hours = Column(DECIMAL(4, 2))
    overtime_hours = Column(DECIMAL(4, 2))
    clock_in_time = Column(DateTime(timezone=True))
    clock_out_time = Column(DateTime(timezone=True))
    supervisor_id = Column(Integer)
    supervisor_name = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    __table_args__ = (
        UniqueConstraint('user_id', 'attendance_summary_date', name='unique_user_summary_date'),
    )