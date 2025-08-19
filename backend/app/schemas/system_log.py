from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.networks import IPvAnyAddress
from app.core.enums import SystemAction
from app.core.exceptions import ValidationError

class SystemLogBase(BaseModel):
    user_id: Optional[int] = Field(None, description="ID of the user performing the action")
    action: SystemAction = Field(..., description="Action performed (e.g., INSERT, UPDATE, DELETE)")
    table_affected: Optional[str] = Field(None, max_length=50, description="Database table affected by the action")
    record_id: Optional[int] = Field(None, description="ID of the affected record")
    old_values: Optional[dict] = Field(None, description="Previous values of the affected record")
    new_values: Optional[dict] = Field(None, description="New values of the affected record")
    ip_address: Optional[IPvAnyAddress] = Field(None, description="IP address of the client")
    user_agent: Optional[str] = Field(None, max_length=255, description="User agent of the client")
    request_id: Optional[str] = Field(None, max_length=36, description="Unique request identifier")
    is_active: bool = Field(True, description="Whether the log is active")

    @field_validator('user_id')
    @classmethod
    def validate_user_id(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValidationError(detail="Invalid user ID")
        return value

    @field_validator('request_id')
    @classmethod
    def validate_request_id(cls, value: Optional[str]) -> Optional[str]:
        if value and not value.replace('-', '').isalnum():
            raise ValidationError(detail="Invalid request ID format")
        return value

    @field_validator('table_affected')
    @classmethod
    def validate_table_affected(cls, value: Optional[str]) -> Optional[str]:
        if value and not value.isidentifier():
            raise ValidationError(detail="Invalid table name")
        return value

class SystemLogCreate(SystemLogBase):
    pass

class SystemLogOut(SystemLogBase):
    log_id: int = Field(..., description="Unique identifier of the log entry")
    timestamp: datetime = Field(..., description="Timestamp of when the log was created")
    deleted_at: Optional[datetime] = Field(None, description="Timestamp when the log was soft deleted")

    @field_validator('timestamp', 'deleted_at')
    @classmethod
    def validate_timezone(cls, value: Optional[datetime], info) -> Optional[datetime]:
        if value and value.tzinfo is None:
            raise ValidationError(detail=f"{info.field_name} must include timezone")
        return value

    model_config = ConfigDict(from_attributes=True)

class SystemLogActionSummary(BaseModel):
    action: str = Field(..., description="Action type (e.g., INSERT, UPDATE, DELETE)")
    count: int = Field(..., ge=0, description="Number of occurrences of the action")
    
    model_config = ConfigDict(from_attributes=True)