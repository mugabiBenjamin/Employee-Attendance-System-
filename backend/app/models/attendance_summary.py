from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, date
from app.models.attendance import AttendanceStatus

class AttendanceSummary(SQLModel, table=True):
    __tablename__ = "attendance_summary"
    user_id: int = Field(primary_key=True)
    employee_id: str
    full_name: str
    department_name: str
    date: Optional[date]
    status: Optional[AttendanceStatus]
    total_hours: Optional[float]
    overtime_hours: Optional[float]
    clock_in_time: Optional[datetime]
    clock_out_time: Optional[datetime]