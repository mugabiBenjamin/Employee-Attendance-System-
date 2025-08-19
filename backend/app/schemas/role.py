from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.core.enums import RoleName, Permission
from app.core.exceptions import ValidationError

class RoleBase(BaseModel):
    role_name: str = Field(..., max_length=50)
    description: Optional[str] = None
    permissions: dict = {}

    @field_validator('role_name')
    @classmethod
    def validate_role_name(cls, value: str) -> str:
        valid_roles = {role.value for role in RoleName}
        if value not in valid_roles:
            raise ValidationError(detail=f"Invalid role name. Must be one of: {', '.join(sorted(valid_roles))}")
        return value

    @field_validator('permissions')
    @classmethod
    def validate_permissions(cls, value: dict) -> dict:
        valid_permissions = {perm.value for perm in Permission}
        invalid_permissions = [p for p in value.keys() if p not in valid_permissions]
        if invalid_permissions:
            raise ValidationError(detail=f"Invalid permissions: {', '.join(invalid_permissions)}")
        return value

class RoleCreate(RoleBase):
    role_name: str
    description: Optional[str] = None
    permissions: dict = {}

class RoleUpdate(BaseModel):
    role_name: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    permissions: Optional[dict] = None

    @field_validator('role_name')
    @classmethod
    def validate_role_name(cls, value: Optional[str]) -> Optional[str]:
        if value:
            valid_roles = {role.value for role in RoleName}
            if value not in valid_roles:
                raise ValidationError(detail=f"Invalid role name. Must be one of: {', '.join(sorted(valid_roles))}")
        return value

    @field_validator('permissions')
    @classmethod
    def validate_permissions(cls, value: Optional[dict]) -> Optional[dict]:
        if value:
            valid_permissions = {perm.value for perm in Permission}
            invalid_permissions = [p for p in value.keys() if p not in valid_permissions]
            if invalid_permissions:
                raise ValidationError(detail=f"Invalid permissions: {', '.join(invalid_permissions)}")
        return value

class RoleOut(RoleBase):
    role_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)