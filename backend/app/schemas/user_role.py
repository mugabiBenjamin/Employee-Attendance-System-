from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class UserRoleBase(BaseModel):
    user_id: int
    role_id: int
    assigned_by: Optional[int] = None
    is_active: bool = True

class UserRoleCreate(UserRoleBase):
    pass

class UserRoleUpdate(UserRoleBase):
    user_id: Optional[int] = None
    role_id: Optional[int] = None
    is_active: Optional[bool] = None

class UserRoleOut(UserRoleBase):
    user_role_id: int
    assigned_at: datetime

    model_config = ConfigDict(from_attributes=True)