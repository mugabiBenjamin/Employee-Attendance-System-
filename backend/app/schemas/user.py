from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr

class UserBase(BaseModel):
    email: EmailStr = Field(..., description="User email address", pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    first_name: str = Field(..., max_length=100, description="User first name")
    last_name: str = Field(..., max_length=100, description="User last name")
    phone: Optional[str] = Field(None, pattern=r'^[\+]?[0-9\s\-\(\)]+$', description="User phone number")
    job_title: Optional[str] = Field(None, max_length=100, description="User job title")
    hire_date: date = Field(..., description="User hire date")
    employee_type: str = Field('full_time', description="User employee type")
    salary: Optional[float] = Field(None, ge=0, description="User salary")
    manager_id: Optional[int] = Field(None, description="User manager ID")
    is_active: bool = Field(True, description="User active status")

class UserCreate(BaseModel):
    email: EmailStr = Field(..., description="User email address", pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    password_hash: str = Field(..., description="Hashed user password")
    first_name: str = Field(..., max_length=100, description="User first name")
    last_name: str = Field(..., max_length=100, description="User last name")
    phone: Optional[str] = Field(None, pattern=r'^[\+]?[0-9\s\-\(\)]+$', description="User phone number")
    job_title: Optional[str] = Field(None, max_length=100, description="User job title")
    hire_date: date = Field(..., description="User hire date")
    employee_type: str = Field('full_time', description="User employee type")
    salary: Optional[float] = Field(None, ge=0, description="User salary")
    manager_id: Optional[int] = Field(None, description="User manager ID")
    is_active: bool = Field(True, description="User active status")

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = Field(None, pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$', description="User email address")
    first_name: Optional[str] = Field(None, max_length=100, description="User first name")
    last_name: Optional[str] = Field(None, max_length=100, description="User last name")
    phone: Optional[str] = Field(None, pattern=r'^[\+]?[0-9\s\-\(\)]+$', description="User phone number")
    job_title: Optional[str] = Field(None, max_length=100, description="User job title")
    employee_type: Optional[str] = Field(None, description="User employee type")
    salary: Optional[float] = Field(None, ge=0, description="User salary")
    manager_id: Optional[int] = Field(None, description="User manager ID")
    is_active: Optional[bool] = Field(None, description="User active status")

class UserOut(UserBase):
    user_id: int = Field(..., description="User ID")
    employee_id: str = Field(..., description="User employee ID")
    last_login: Optional[datetime] = Field(None, description="User last login timestamp")
    created_at: datetime = Field(..., description="User creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="User update timestamp")
    
    model_config = ConfigDict(from_attributes=True)