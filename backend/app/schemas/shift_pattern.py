
from datetime import datetime, time
from typing import Optional
from pydantic import BaseModel, Field

class ShiftPatternBase(BaseModel):
    pattern_name: str = Field(..., max_length=100)
    shift_type: str
    start_time: time
    end_time: time
    break_duration: int = Field(0, ge=0)
    is_overnight: bool = False
    is_active: bool = True

class ShiftPatternCreate(ShiftPatternBase):
    pass

class ShiftPatternUpdate(BaseModel):
    pattern_name: Optional[str] = Field(None, max_length=100)
    shift_type: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    break_duration: Optional[int] = Field(None, ge=0)
    is_overnight: Optional[bool] = None
    is_active: Optional[bool] = None

class ShiftPatternOut(ShiftPatternBase):
    pattern_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True