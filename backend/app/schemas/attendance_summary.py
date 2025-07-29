from datetime import datetime, date as dt
from typing import Optional
from pydantic import BaseModel, ConfigDict

class AttendanceSummaryOut(BaseModel):
    user_id: int
    employee_id: Optional[str] = None
    full_name: Optional[str] = None
    department_name: Optional[str] = None
    date: Optional[dt] = None
    status: Optional[str] = None
    total_hours: Optional[str] = None
    overtime_hours: Optional[str] = None
    clock_in_time: Optional[datetime] = None
    clock_out_time: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)