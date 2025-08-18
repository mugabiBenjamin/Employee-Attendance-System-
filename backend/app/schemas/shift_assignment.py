from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class ShiftAssignmentBase(BaseModel):
    user_id: int = Field(..., description="ID of the user assigned to the shift")
    pattern_id: int = Field(..., description="ID of the shift pattern")
    effective_from: date = Field(..., description="Date the shift assignment starts")
    effective_to: Optional[date] = Field(None, description="Date the shift assignment ends")
    is_active: bool = Field(True, description="Whether the shift assignment is active")

class ShiftAssignmentCreate(ShiftAssignmentBase):
    pass

class ShiftAssignmentUpdate(BaseModel):
    pattern_id: Optional[int] = Field(None, description="ID of the shift pattern to update")
    effective_from: Optional[date] = Field(None, description="Date the shift assignment starts to update")
    effective_to: Optional[date] = Field(None, description="Date the shift assignment ends to update")
    is_active: Optional[bool] = Field(None, description="Whether the shift assignment is active to update")

class ShiftAssignmentOut(ShiftAssignmentBase):
    assignment_id: int = Field(..., description="Unique identifier of the shift assignment")
    created_at: datetime = Field(..., description="Timestamp when the shift assignment was created")
    updated_at: Optional[datetime] = Field(None, description="Timestamp when the shift assignment was last updated")
    
    model_config = ConfigDict(from_attributes=True)