from typing import Optional
from pydantic import BaseModel, EmailStr, validator
from datetime import datetime, date

class UserBase(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    phone: Optional[str] = None
    employee_type: str = "full_time"

    @validator("phone", allow_reuse=True)
    def validate_phone(cls, v):
        if v is not None and not v:
            raise ValueError("Phone number cannot be empty if provided")
        import re
        pattern = r'^[\+]?[0-9\s\-\(\)]+$'
        if v is not None and not re.match(pattern, v):
            raise ValueError("Invalid phone number format")
        return v

class UserCreate(UserBase):
    password: str
    hire_date: date
    salary: Optional[float] = None
    manager_id: Optional[int] = None

    @validator("password", allow_reuse=True)
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

class UserUpdate(UserBase):
    password: Optional[str] = None
    hire_date: Optional[date] = None
    salary: Optional[float] = None
    manager_id: Optional[int] = None
    is_active: Optional[bool] = None

    @validator("password", allow_reuse=True)
    def validate_password(cls, v):
        if v is not None and len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

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
    password: str

    @validator("password", allow_reuse=True)
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"