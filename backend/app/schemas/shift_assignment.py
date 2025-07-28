
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, ConfigDict

class ShiftAssignmentBase(BaseModel):
    user_id: int
    pattern_id: int
    effective_from: date
    effective_to: Optional[date] = None
    is_active: bool = True

class ShiftAssignmentCreate(ShiftAssignmentBase):
    pass

class ShiftAssignmentUpdate(BaseModel):
    pattern_id: Optional[int] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    is_active: Optional[bool] = None

class ShiftAssignmentOut(ShiftAssignmentBase):
    assignment_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)