from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator
from app.core.enums import AttendanceStatus
from app.core.exceptions import ValidationError

class AttendanceSummaryOut(BaseModel):
    user_id: int
    employee_id: Optional[str] = None
    full_name: Optional[str] = None
    department_name: Optional[str] = None
    attendance_summary_date: Optional[date] = None
    status: Optional[AttendanceStatus] = None
    total_hours: Optional[float] = None
    overtime_hours: Optional[float] = None
    clock_in_time: Optional[datetime] = None
    clock_out_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
            # time: lambda v: v.isoformat() if v else None,
            # Decimal: lambda v: float(v) if v is not None else None
        },
        arbitrary_types_allowed=True
    )

    @field_validator('attendance_summary_date')
    @classmethod
    def validate_date(cls, value: Optional[date]) -> Optional[date]:
        if value and value > date.today():
            raise ValidationError(detail="Attendance summary date cannot be in the future.")
        return value