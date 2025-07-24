from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class UserDepartmentBase(BaseModel):
    user_id: int
    department_id: int
    is_primary: bool = False

class UserDepartmentCreate(UserDepartmentBase):
    pass

class UserDepartmentUpdate(UserDepartmentBase):
    user_id: Optional[int] = None
    department_id: Optional[int] = None
    is_primary: Optional[bool] = None

class UserDepartmentOut(UserDepartmentBase):
    user_department_id: int
    assigned_at: datetime

    model_config = ConfigDict(from_attributes=True)