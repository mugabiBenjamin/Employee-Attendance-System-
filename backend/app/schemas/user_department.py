from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional

class UserDepartmentBase(BaseModel):
    user_id: int = Field(..., description="ID of the user assigned to the department")
    department_id: int = Field(..., description="ID of the department the user is assigned to")
    is_primary: bool = Field(False, description="Whether this is the user's primary department")

class UserDepartmentCreate(UserDepartmentBase):
    pass

class UserDepartmentUpdate(BaseModel):
    user_id: Optional[int] = Field(None, description="ID of the user to update")
    department_id: Optional[int] = Field(None, description="ID of the department to update")
    is_primary: Optional[bool] = Field(None, description="Whether this is the user's primary department to update")

class UserDepartmentOut(UserDepartmentBase):
    user_department_id: int = Field(..., description="Unique identifier of the user-department assignment")
    assigned_at: datetime = Field(..., description="Timestamp when the user was assigned to the department")
    updated_at: Optional[datetime] = Field(None, description="Timestamp when the assignment was last updated")
    
    model_config = ConfigDict(from_attributes=True)