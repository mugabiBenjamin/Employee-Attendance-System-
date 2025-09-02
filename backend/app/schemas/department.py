from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from decimal import Decimal
from app.core.exceptions import ValidationError

class DepartmentBase(BaseModel):
    department_name: str = Field(..., max_length=100, description="Name of the department")
    description: Optional[str] = Field(None, description="Description of the department")
    supervisor_id: Optional[int] = Field(None, description="ID of the user managing the department")
    budget: Optional[Decimal] = Field(None, ge=0, description="Department budget")
    location: Optional[str] = Field(None, max_length=255, description="Department location")
    is_active: bool = Field(True, description="Whether the department is active")

    @field_validator('department_name')
    @classmethod
    def validate_department_name(cls, value: str) -> str:
        if not value.strip():
            raise ValidationError(detail="Department name cannot be empty")
        return value

    @field_validator('supervisor_id')
    @classmethod
    def validate_supervisor_id(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValidationError(detail="Invalid manager ID")
        return value

class DepartmentCreate(DepartmentBase):
    pass

class DepartmentUpdate(BaseModel):
    department_name: Optional[str] = Field(None, max_length=100, description="Updated name of the department")
    description: Optional[str] = Field(None, description="Updated description of the department")
    supervisor_id: Optional[int] = Field(None, description="Updated ID of the user managing the department")
    budget: Optional[Decimal] = Field(None, ge=0, description="Updated department budget")
    location: Optional[str] = Field(None, max_length=255, description="Updated department location")
    is_active: Optional[bool] = Field(None, description="Updated active status of the department")

    @field_validator('department_name')
    @classmethod
    def validate_department_name(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValidationError(detail="Department name cannot be empty")
        return value

    @field_validator('supervisor_id')
    @classmethod
    def validate_supervisor_id(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValidationError(detail="Invalid manager ID")
        return value

class DepartmentOut(DepartmentBase):
    department_id: int = Field(..., description="Unique identifier of the department")
    created_at: datetime = Field(..., description="Timestamp when the department was created")
    updated_at: Optional[datetime] = Field(None, description="Timestamp when the department was last updated")
    
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None,
            Decimal: lambda v: float(v) if v is not None else None
        },
        arbitrary_types_allowed=True
    )