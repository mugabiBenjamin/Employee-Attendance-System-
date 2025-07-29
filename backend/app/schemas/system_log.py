from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from pydantic.networks import IPvAnyAddress
from app.core.enums import SystemAction

class SystemLogBase(BaseModel):
    user_id: Optional[int] = None
    action: str
    table_affected: Optional[str] = Field(None, max_length=50)
    record_id: Optional[int] = None
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    ip_address: Optional[IPvAnyAddress | str] = None
    user_agent: Optional[str] = None

class SystemLogCreate(SystemLogBase):
    user_id: Optional[int] = None
    action: SystemAction
    table_affected: Optional[str] = None
    record_id: Optional[int] = None
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    ip_address: Optional[str] = None

class SystemLogOut(SystemLogBase):
    log_id: int
    timestamp: datetime
    
    model_config = ConfigDict(from_attributes=True)