from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class EmployeeHierarchyBase(BaseModel):
    employee_id: int
    manager_id: int
    level: int = Field(1, ge=1, le=10)
    effective_from: date
    effective_to: Optional[date] = None

class EmployeeHierarchyCreate(EmployeeHierarchyBase):
    employee_id: int
    manager_id: int

class EmployeeHierarchyUpdate(BaseModel):
    manager_id: Optional[int] = None
    level: Optional[int] = Field(None, ge=1, le=10)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None

class EmployeeHierarchyOut(EmployeeHierarchyBase):
    hierarchy_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)