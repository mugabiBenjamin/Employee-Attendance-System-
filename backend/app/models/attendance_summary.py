from sqlalchemy import Column, Integer, String, DateTime, Date
from app.core.database import Base

class AttendanceSummary(Base):
    __tablename__ = "attendance_summary"
    
    user_id = Column(Integer, primary_key=True)
    employee_id = Column(String)
    full_name = Column(String)
    department_name = Column(String)
    date = Column(Date)
    status = Column(String)
    total_hours = Column(String)
    overtime_hours = Column(String)  
    clock_in_time = Column(DateTime(timezone=True))
    clock_out_time = Column(DateTime(timezone=True))