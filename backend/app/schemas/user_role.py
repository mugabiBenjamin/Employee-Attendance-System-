from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class UserRoleBase(BaseModel):
    user_id: int
    role_id: int
    assigned_by: Optional[int] = None
    is_active: bool = True

class UserRoleCreate(UserRoleBase):
    user_id: int
    role_id: int
    is_active: bool = True

class UserRoleUpdate(BaseModel):
    user_id: Optional[int] = None
    role_id: Optional[int] = None
    assigned_by: Optional[int] = None
    is_active: Optional[bool] = None

class UserRoleOut(UserRoleBase):
    user_role_id: int
    user_id: int
    role_id: int
    assigned_by: Optional[int]
    is_active: bool
    assigned_at: datetime
    updated_at: Optional[datetime] = None
    
class UserProfile(BaseModel):
    user_id: int
    email: str
    first_name: str
    last_name: str
    job_title: str | None
    roles: list[str] = []
    permissions: list[str] = []
    model_config = ConfigDict(from_attributes=True)