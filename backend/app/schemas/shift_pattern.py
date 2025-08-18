from datetime import datetime, time
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.core.enums import ShiftType

class ShiftPatternBase(BaseModel):
    pattern_name: str = Field(..., max_length=100, description="Name of the shift pattern")
    shift_type: ShiftType = Field(..., description="Type of shift (e.g., STANDARD, NIGHT)")
    start_time: time = Field(..., description="Start time of the shift")
    end_time: time = Field(..., description="End time of the shift")
    break_duration: int = Field(0, ge=0, description="Break duration in minutes")
    is_overnight: bool = Field(False, description="Whether the shift spans midnight")
    is_active: bool = Field(True, description="Whether the shift pattern is active")

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

class ShiftPatternOut(ShiftPatternBase):
    pattern_id: int = Field(..., description="Unique identifier of the shift pattern")
    created_at: datetime = Field(..., description="Timestamp when the shift pattern was created")
    updated_at: Optional[datetime] = Field(None, description="Timestamp when the shift pattern was last updated")
    
    model_config = ConfigDict(from_attributes=True)