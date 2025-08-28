from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import datetime
from typing import Optional
from app.core.exceptions import ValidationError

class UserDepartmentBase(BaseModel):
    user_id: int = Field(..., description="ID of the user assigned to the department")
    department_id: int = Field(..., description="ID of the department the user is assigned to")
    assigned_by: Optional[int] = Field(None, description="ID of the user who assigned the department")
    is_primary: bool = Field(False, description="Whether this is the user's primary department")
    is_active: bool = Field(True, description="Whether the department assignment is active")

    @field_validator('user_id', 'assigned_by')
    @classmethod
    def validate_user_id(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValidationError(detail="Invalid user ID")
        return value

    @field_validator('department_id')
    @classmethod
    def validate_department_id(cls, value: int) -> int:
        if value <= 0:
            raise ValidationError(detail="Invalid department ID")
        return value

class UserDepartmentCreate(UserDepartmentBase):
    pass

class UserDepartmentUpdate(BaseModel):
    user_id: Optional[int] = Field(None, description="Updated ID of the user")
    department_id: Optional[int] = Field(None, description="Updated ID of the department")
    assigned_by: Optional[int] = Field(None, description="Updated ID of the user who assigned the department")
    is_primary: Optional[bool] = Field(None, description="Updated primary department status")
    is_active: Optional[bool] = Field(None, description="Updated active status of the department assignment")

    @field_validator('user_id', 'assigned_by')
    @classmethod
    def validate_user_id(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValidationError(detail="Invalid user ID")
        return value

    @field_validator('department_id')
    @classmethod
    def validate_department_id(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValidationError(detail="Invalid department ID")
        return value

class UserDepartmentOut(UserDepartmentBase):
    user_department_id: int = Field(..., description="Unique identifier of the user-department assignment")
    assigned_at: datetime = Field(..., description="Timestamp when the user was assigned to the department")
    updated_at: Optional[datetime] = Field(None, description="Timestamp when the assignment was last updated")
    
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()}
    )