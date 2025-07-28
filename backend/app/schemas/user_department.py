from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class UserDepartmentBase(BaseModel):
    user_id: int
    department_id: int
    is_primary: bool = False

class UserDepartmentCreate(UserDepartmentBase):
    user_id: int
    department_id: int
    is_primary: bool = False

class UserDepartmentUpdate(BaseModel):
    user_id: Optional[int] = None
    department_id: Optional[int] = None
    is_primary: Optional[bool] = None

class UserDepartmentOut(UserDepartmentBase):
    user_department_id: int
    user_id: int
    department_id: int
    is_primary: bool
    assigned_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)