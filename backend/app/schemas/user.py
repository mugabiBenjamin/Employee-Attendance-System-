from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator
from app.core.enums import EmployeeType
from app.core.exceptions import ValidationError

class UserCreate(BaseModel):
    email: EmailStr = Field(..., description="User email address", pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    password: str = Field(..., description="User password")
    first_name: str = Field(..., max_length=100, description="User first name")
    last_name: str = Field(..., max_length=100, description="User last name")
    phone: Optional[str] = Field(None, pattern=r'^[\+]?[0-9\s\-\(\)]+$', description="User phone number")
    job_title: Optional[str] = Field(None, max_length=100, description="User job title")
    hire_date: date = Field(..., description="User hire date")
    employee_type: str = Field('full_time', description="User employee type")
    salary: Optional[float] = Field(None, ge=0, description="User salary")
    manager_id: Optional[int] = Field(None, description="User manager ID")
    is_active: bool = Field(True, description="User active status")

    @field_validator('hire_date')
    @classmethod
    def validate_hire_date(cls, value: date) -> date:
        if value > date.today():
            raise ValidationError(detail="Hire date cannot be in the future.")
        return value

    @field_validator('employee_type')
    @classmethod
    def validate_employee_type(cls, value: str) -> str:
        if value not in [e.value for e in EmployeeType]:
            raise ValidationError(detail=f"Invalid employee_type. Must be one of: {[e.value for e in EmployeeType]}")
        return value

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
    hire_date: Optional[date] = Field(None, description="User hire date")

    @field_validator('hire_date')
    @classmethod
    def validate_hire_date(cls, value: Optional[date]) -> Optional[date]:
        if value and value > date.today():
            raise ValidationError(detail="Hire date cannot be in the future.")
        return value

    @field_validator('employee_type')
    @classmethod
    def validate_employee_type(cls, value: Optional[str]) -> Optional[str]:
        if value and value not in [e.value for e in EmployeeType]:
            raise ValidationError(detail=f"Invalid employee_type. Must be one of: {[e.value for e in EmployeeType]}")
        return value

class UserOut(BaseModel):
    user_id: int = Field(..., description="User ID")
    email: EmailStr = Field(..., description="User email address")
    first_name: str = Field(..., description="User first name")
    last_name: str = Field(..., description="User last name")
    phone: Optional[str] = Field(None, description="User phone number")
    job_title: Optional[str] = Field(None, description="User job title")
    hire_date: date = Field(..., description="User hire date")
    employee_type: str = Field(..., description="User employee type")
    salary: Optional[float] = Field(None, description="User salary")
    manager_id: Optional[int] = Field(None, description="User manager ID")
    is_active: bool = Field(..., description="User active status")
    employee_id: str = Field(..., description="User employee ID")
    last_login: Optional[datetime] = Field(None, description="User last login timestamp")
    created_at: datetime = Field(..., description="User creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="User update timestamp")
    
    model_config = ConfigDict(from_attributes=True)