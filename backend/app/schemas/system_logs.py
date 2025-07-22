from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.core.enums import SystemAction

class SystemLogResponse(BaseModel):
    log_id: int
    user_id: Optional[int] = None
    action: SystemAction
    table_affected: Optional[str] = None
    record_id: Optional[int] = None
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    timestamp: datetime

    class Config:
        from_attributes = True
        use_enum_values = True