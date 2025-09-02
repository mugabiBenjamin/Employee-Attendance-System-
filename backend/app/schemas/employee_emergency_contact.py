from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.core.exceptions import ValidationError

class EmployeeEmergencyContactBase(BaseModel):
    user_id: int = Field(..., description="ID of the user associated with the emergency contact")
    contact_name: str = Field(..., max_length=255, description="Name of the emergency contact")
    relationship: str = Field(..., max_length=100, description="Relationship to the employee")
    phone: str = Field(..., pattern=r'^[\+]?[0-9\s\-\(\)]{7,20}$', description="Primary phone number")
    alternate_phone: Optional[str] = Field(None, pattern=r'^[\+]?[0-9\s\-\(\)]{7,20}$', description="Alternate phone number")
    email: Optional[str] = Field(None, pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$', description="Email address")
    address: Optional[str] = Field(None, description="Physical address")
    is_primary: bool = Field(False, description="Whether this is the primary contact")
    is_active: bool = Field(True, description="Whether the contact is active")

    @field_validator('user_id')
    @classmethod
    def validate_user_id(cls, value: int) -> int:
        if value <= 0:
            raise ValidationError(detail="Invalid user ID")
        return value

class EmployeeEmergencyContactCreate(BaseModel):
    contact_name: str = Field(..., max_length=255, description="Name of the emergency contact")
    relationship: str = Field(..., max_length=100, description="Relationship to the employee")
    phone: str = Field(..., pattern=r'^[\+]?[0-9\s\-\(\)]{7,20}$', description="Primary phone number")
    alternate_phone: Optional[str] = Field(None, pattern=r'^[\+]?[0-9\s\-\(\)]{7,20}$', description="Alternate phone number")
    email: Optional[str] = Field(None, pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$', description="Email address")
    address: Optional[str] = Field(None, description="Physical address")
    is_primary: bool = Field(False, description="Whether this is the primary contact")
    
    # Prevent clients from submitting unexpected fields like `user_id` or `is_active`
    model_config = ConfigDict(extra="forbid")

class EmployeeEmergencyContactUpdate(BaseModel):
    contact_name: Optional[str] = Field(None, max_length=255, description="Updated name of the emergency contact")
    relationship: Optional[str] = Field(None, max_length=100, description="Updated relationship to the employee")
    phone: Optional[str] = Field(None, pattern=r'^[\+]?[0-9\s\-\(\)]{7,20}$', description="Updated primary phone number")
    alternate_phone: Optional[str] = Field(None, pattern=r'^[\+]?[0-9\s\-\(\)]{7,20}$', description="Updated alternate phone number")
    email: Optional[str] = Field(None, pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$', description="Updated email address")
    address: Optional[str] = Field(None, description="Updated physical address")
    is_primary: Optional[bool] = Field(None, description="Updated primary contact status")
    is_active: Optional[bool] = Field(None, description="Updated active status")

class EmployeeEmergencyContactOut(EmployeeEmergencyContactBase):
    contact_id: int = Field(..., description="Unique identifier of the emergency contact")
    created_at: datetime = Field(..., description="Timestamp when the contact was created")
    updated_at: Optional[datetime] = Field(None, description="Timestamp when the contact was last updated")

    @field_validator('created_at', 'updated_at')
    @classmethod
    def validate_timezone(cls, value: Optional[datetime], info) -> Optional[datetime]:
        if value and value.tzinfo is None:
            raise ValidationError(detail=f"{info.field_name} must include timezone")
        return value

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None,
        },
        arbitrary_types_allowed=True
    )