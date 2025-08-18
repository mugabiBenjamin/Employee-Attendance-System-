from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class HolidayCalendarBase(BaseModel):
    holiday_name: str = Field(..., max_length=100)
    holiday_date: date
    description: Optional[str] = None
    is_recurring: bool = False
    applies_to_all: bool = True
    department_id: Optional[int] = None
    year: int = Field(..., ge=2020, le=2050)

class HolidayCalendarCreate(HolidayCalendarBase):
    date: datetime = Field(..., alias="date")
    holiday_name: str
    description: Optional[str] = None
    is_recurring: bool = False
    department_id: Optional[int] = None

class HolidayCalendarUpdate(BaseModel):
    holiday_name: Optional[str] = Field(None, max_length=100)
    holiday_date: Optional[date] = None
    description: Optional[str] = None
    is_recurring: Optional[bool] = None
    applies_to_all: Optional[bool] = None
    department_id: Optional[int] = None
    year: Optional[int] = Field(None, ge=2020, le=2050)

class HolidayCalendarOut(HolidayCalendarBase):
    holiday_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)