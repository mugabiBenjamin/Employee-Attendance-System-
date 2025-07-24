from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class DepartmentBase(BaseModel):
    department_name: str = Field(..., max_length=100)
    description: Optional[str] = None
    manager_id: Optional[int] = None
    budget: Optional[float] = Field(None, ge=0)
    location: Optional[str] = Field(None, max_length=255)
    is_active: bool = True

class DepartmentCreate(DepartmentBase):
    pass

class DepartmentUpdate(BaseModel):
    department_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    manager_id: Optional[int] = None
    budget: Optional[float] = Field(None, ge=0)
    location: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None

class DepartmentOut(DepartmentBase):
    department_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True