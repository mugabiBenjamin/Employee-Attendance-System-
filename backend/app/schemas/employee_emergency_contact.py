from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class EmployeeEmergencyContactBase(BaseModel):
    user_id: int
    contact_name: str = Field(..., max_length=255)
    relationship: str = Field(..., max_length=100)
    phone: str = Field(..., regex=r'^[\+]?[0-9\s\-\(\)]+$')
    email: Optional[str] = Field(None, regex=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    address: Optional[str] = None
    is_primary: bool = False

class EmployeeEmergencyContactCreate(EmployeeEmergencyContactBase):
    pass

class EmployeeEmergencyContactUpdate(BaseModel):
    contact_name: Optional[str] = Field(None, max_length=255)
    relationship: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, regex=r'^[\+]?[0-9\s\-\(\)]+$')
    email: Optional[str] = Field(None, regex=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    address: Optional[str] = None
    is_primary: Optional[bool] = None

class EmployeeEmergencyContactOut(EmployeeEmergencyContactBase):
    contact_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)