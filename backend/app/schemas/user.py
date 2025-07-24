from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field

class UserBase(BaseModel):
    email: str = Field(..., regex=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    first_name: str = Field(..., max_length=100)
    last_name: str = Field(..., max_length=100)
    phone: Optional[str] = Field(None, regex=r'^[\+]?[0-9\s\-\(\)]+$')
    hire_date: date
    employee_type: str = 'full_time'
    salary: Optional[float] = Field(None, ge=0)
    manager_id: Optional[int] = None
    is_active: bool = True

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[str] = Field(None, regex=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, regex=r'^[\+]?[0-9\s\-\(\)]+$')
    employee_type: Optional[str] = None
    salary: Optional[float] = Field(None, ge=0)
    manager_id: Optional[int] = None
    is_active: Optional[bool] = None

class UserOut(UserBase):
    user_id: int
    employee_id: str
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True