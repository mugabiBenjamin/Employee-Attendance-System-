from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import date, datetime
from typing import Optional, List
from app.core.exceptions import ValidationError

class UserRoleBase(BaseModel):
    user_id: int = Field(..., description="ID of the user assigned to the role")
    role_id: int = Field(..., description="ID of the role assigned to the user")
    assigned_by: Optional[int] = Field(None, description="ID of the user who assigned the role")
    is_active: bool = Field(True, description="Whether the role assignment is active")

    @field_validator('user_id', 'assigned_by')
    @classmethod
    def validate_user_id(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValidationError(detail="Invalid user ID")
        return value

    @field_validator('role_id')
    @classmethod
    def validate_role_id(cls, value: int) -> int:
        if value <= 0:
            raise ValidationError(detail="Invalid role ID")
        return value

class UserRoleCreate(UserRoleBase):
    pass

class UserRoleUpdate(BaseModel):
    user_id: Optional[int] = Field(None, description="Updated ID of the user")
    role_id: Optional[int] = Field(None, description="Updated ID of the role")
    assigned_by: Optional[int] = Field(None, description="Updated ID of the user who assigned the role")
    is_active: Optional[bool] = Field(None, description="Updated active status of the role assignment")

    @field_validator('user_id', 'assigned_by')
    @classmethod
    def validate_user_id(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValidationError(detail="Invalid user ID")
        return value

    @field_validator('role_id')
    @classmethod
    def validate_role_id(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValidationError(detail="Invalid role ID")
        return value

class UserRoleOut(UserRoleBase):
    user_role_id: int = Field(..., description="Unique identifier of the user-role assignment")
    assigned_at: datetime = Field(..., description="Timestamp when the role was assigned")
    updated_at: Optional[datetime] = Field(None, description="Timestamp when the role assignment was last updated")
    
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()}
    )

class UserProfile(BaseModel):
    user_id: int = Field(..., description="ID of the user")
    email: str = Field(..., description="Email address of the user")
    first_name: str = Field(..., description="First name of the user")
    last_name: str = Field(..., description="Last name of the user")
    job_title: Optional[str] = Field(None, description="Job title of the user")
    roles: List[str] = Field(default_factory=list, description="List of role names assigned to the user")
    permissions: dict = Field(default_factory=dict, description="Permissions granted to the user")
    