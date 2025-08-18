from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class RoleBase(BaseModel):
    role_name: str = Field(..., max_length=50)
    description: Optional[str] = None
    permissions: dict = {}

class RoleCreate(RoleBase):
    role_name: str
    description: Optional[str] = None
    permissions: dict = {}

class RoleUpdate(BaseModel):
    role_name: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    permissions: Optional[dict] = None

class RoleOut(RoleBase):
    role_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)