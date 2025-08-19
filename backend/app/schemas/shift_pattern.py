from datetime import datetime, time
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator, ValidationInfo
from app.core.enums import ShiftType
from app.core.exceptions import ValidationError

class ShiftPatternBase(BaseModel):
    pattern_name: str = Field(..., max_length=100, description="Name of the shift pattern")
    shift_type: ShiftType = Field(..., description="Type of shift (e.g., STANDARD, NIGHT)")
    start_time: time = Field(..., description="Start time of the shift")
    end_time: time = Field(..., description="End time of the shift")
    break_duration: int = Field(0, ge=0, description="Break duration in minutes")
    is_overnight: bool = Field(False, description="Whether the shift spans midnight")
    is_active: bool = Field(True, description="Whether the shift pattern is active")

    @field_validator('start_time', 'end_time')
    @classmethod
    def validate_shift_times(cls, value: time, info: ValidationInfo) -> time:
        if 'start_time' in info.data and 'end_time' in info.data and not info.data.get('is_overnight', False):
            start_time = info.data['start_time']
            end_time = info.data['end_time']
            if start_time >= end_time:
                raise ValidationError(detail="End time must be after start time for non-overnight shifts")
        return value

class ShiftPatternCreate(ShiftPatternBase):
    pass

class ShiftPatternUpdate(BaseModel):
    pattern_name: Optional[str] = Field(None, max_length=100, description="Name of the shift pattern to update")
    shift_type: Optional[ShiftType] = Field(None, description="Type of shift to update")
    start_time: Optional[time] = Field(None, description="Start time of the shift to update")
    end_time: Optional[time] = Field(None, description="End time of the shift to update")
    break_duration: Optional[int] = Field(None, ge=0, description="Break duration in minutes to update")
    is_overnight: Optional[bool] = Field(None, description="Whether the shift spans midnight to update")
    is_active: Optional[bool] = Field(None, description="Whether the shift pattern is active to update")

    @field_validator('start_time', 'end_time')
    @classmethod
    def validate_shift_times(cls, value: Optional[time], info: ValidationInfo) -> Optional[time]:
        if 'start_time' in info.data and 'end_time' in info.data and not info.data.get('is_overnight', False):
            start_time = info.data['start_time']
            end_time = info.data['end_time']
            if start_time >= end_time:
                raise ValidationError(detail="End time must be after start time for non-overnight shifts")
        return value

class ShiftPatternOut(ShiftPatternBase):
    pattern_id: int = Field(..., description="Unique identifier of the shift pattern")
    created_at: datetime = Field(..., description="Timestamp when the shift pattern was created")
    updated_at: Optional[datetime] = Field(None, description="Timestamp when the shift pattern was last updated")

    @field_validator('pattern_id')
    @classmethod
    def validate_pattern_id(cls, value: int) -> int:
        if value <= 0:
            raise ValidationError(detail="Invalid pattern_id")
        return value

    @field_validator('created_at', 'updated_at')
    @classmethod
    def validate_timezone(cls, value: Optional[datetime], info: ValidationInfo) -> Optional[datetime]:
        if value and value.tzinfo is None:
            raise ValidationError(detail=f"{info.field_name.capitalize()} must include timezone")
        return value

    model_config = ConfigDict(from_attributes=True)