from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from pydantic.networks import IPvAnyAddress
from app.core.enums import SystemAction

class SystemLogBase(BaseModel):
    user_id: Optional[int] = Field(None, description="ID of the user performing the action")
    action: str = Field(..., description="Action performed (e.g., INSERT, UPDATE, DELETE)")
    table_affected: Optional[str] = Field(None, max_length=50, description="Database table affected by the action")
    record_id: Optional[int] = Field(None, description="ID of the affected record")
    old_values: Optional[dict] = Field(None, description="Previous values of the affected record")
    new_values: Optional[dict] = Field(None, description="New values of the affected record")
    ip_address: Optional[IPvAnyAddress | str] = Field(None, description="IP address of the client")
    user_agent: Optional[str] = Field(None, max_length=255, description="User agent of the client")
    request_id: Optional[str] = Field(None, max_length=36, description="Unique request identifier")
    is_active: bool = Field(True, description="Whether the log is active")

class SystemLogCreate(SystemLogBase):
    action: SystemAction = Field(..., description="Action performed, validated against SystemAction enum")

class SystemLogOut(SystemLogBase):
    log_id: int = Field(..., description="Unique identifier of the log entry")
    timestamp: datetime = Field(..., description="Timestamp of when the log was created")
    
    model_config = ConfigDict(from_attributes=True)

class SystemLogActionSummary(BaseModel):
    action: str = Field(..., description="Action type (e.g., INSERT, UPDATE, DELETE)")
    count: int = Field(..., ge=0, description="Number of occurrences of the action")
    
    model_config = ConfigDict(from_attributes=True)