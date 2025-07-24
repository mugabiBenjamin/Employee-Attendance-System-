from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class SystemLogBase(BaseModel):
    user_id: Optional[int] = None
    action: str
    table_affected: Optional[str] = Field(None, max_length=50)
    record_id: Optional[int] = None
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

class SystemLogCreate(SystemLogBase):
    pass

class SystemLogOut(SystemLogBase):
    log_id: int
    timestamp: datetime
    
    class Config:
        from_attributes = True