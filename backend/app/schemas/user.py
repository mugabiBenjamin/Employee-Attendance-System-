from typing import Optional
from pydantic import BaseModel, EmailStr, constr
from datetime import datetime, date

class UserBase(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    phone: Optional[constr(pattern=r'^[\+]?[0-9\s\-\(\)]+$')] = None
    employee_type: str = "full_time"

class UserCreate(UserBase):
    password: constr(min_length=8)
    hire_date: date
    salary: Optional[float] = None
    manager_id: Optional[int] = None

class UserUpdate(UserBase):
    password: Optional[constr(min_length=8)] = None
    hire_date: Optional[date] = None
    salary: Optional[float] = None
    manager_id: Optional[int] = None
    is_active: Optional[bool] = None

class UserOut(UserBase):
    user_id: int
    employee_id: str
    hire_date: date
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class UserAuth(BaseModel):
    email: EmailStr
    password: constr(min_length=8)

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"