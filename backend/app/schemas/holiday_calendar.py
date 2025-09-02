from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.core.exceptions import ValidationError

class HolidayCalendarBase(BaseModel):
    holiday_name: str = Field(..., max_length=100, description="Name of the holiday")
    holiday_date: date = Field(..., description="Date of the holiday")
    description: Optional[str] = Field(None, max_length=255, description="Description of the holiday")
    is_recurring: bool = Field(False, description="Whether the holiday recurs annually")
    applies_to_all: bool = Field(True, description="Whether the holiday applies to all departments")
    department_id: Optional[int] = Field(None, description="ID of the department if not applies_to_all")
    year: int = Field(..., ge=2020, le=2050, description="Year of the holiday")

    @field_validator('department_id')
    @classmethod
    def validate_department_id(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValidationError(detail="Invalid department ID")
        return value

    @field_validator('holiday_date')
    @classmethod
    def validate_holiday_date(cls, value: date, values) -> date:
        if 'year' in values and value.year != values['year']:
            raise ValidationError(detail="Holiday date year must match specified year")
        return value

class HolidayCalendarCreate(HolidayCalendarBase):
    holiday_name: str
    holiday_date: date
    description: Optional[str] = None
    is_recurring: bool = False
    department_id: Optional[int] = None

class HolidayCalendarUpdate(BaseModel):
    holiday_name: Optional[str] = Field(None, max_length=100, description="Updated holiday name")
    holiday_date: Optional[date] = Field(None, description="Updated holiday date")
    description: Optional[str] = Field(None, max_length=255, description="Updated description")
    is_recurring: Optional[bool] = Field(None, description="Updated recurrence status")
    applies_to_all: Optional[bool] = Field(None, description="Updated applies_to_all status")
    department_id: Optional[int] = Field(None, description="Updated department ID")
    year: Optional[int] = Field(None, ge=2020, le=2050, description="Updated year")

    @field_validator('department_id')
    @classmethod
    def validate_department_id(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValidationError(detail="Invalid department ID")
        return value

    @field_validator('holiday_date')
    @classmethod
    def validate_holiday_date(cls, value: Optional[date], values) -> Optional[date]:
        if value and 'year' in values and values['year'] and value.year != values['year']:
            raise ValidationError(detail="Holiday date year must match specified year")
        return value

class HolidayCalendarOut(HolidayCalendarBase):
    holiday_id: int = Field(..., description="Unique identifier of the holiday")
    created_at: datetime = Field(..., description="Timestamp when the holiday was created")
    updated_at: Optional[datetime] = Field(None, description="Timestamp when the holiday was last updated")

    @field_validator('created_at', 'updated_at')
    @classmethod
    def validate_timezone(cls, value: Optional[datetime], info) -> Optional[datetime]:
        if value and value.tzinfo is None:
            raise ValidationError(detail=f"{info.field_name} must include timezone")
        return value

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()}
    )