from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, ValidationInfo
from app.core.exceptions import ValidationError

class ShiftAssignmentBase(BaseModel):
    user_id: int = Field(..., description="ID of the user assigned to the shift")
    pattern_id: int = Field(..., description="ID of the shift pattern")
    effective_from: date = Field(..., description="Date the shift assignment starts")
    effective_to: Optional[date] = Field(None, description="Date the shift assignment ends")
    is_active: bool = Field(True, description="Whether the shift assignment is active")

    @field_validator('user_id', 'pattern_id')
    @classmethod
    def validate_ids(cls, value: int, info: ValidationInfo) -> int:
        if value <= 0:
            field = 'user_id' if info.field_name == 'user_id' else 'pattern_id'
            raise ValidationError(detail=f"Invalid {field}")
        return value

    @field_validator('effective_from', 'effective_to')
    @classmethod
    def validate_dates(cls, value: Optional[date], info: ValidationInfo) -> Optional[date]:
        if info.field_name == 'effective_to' and value is not None:
            effective_from = info.data.get('effective_from')
            if effective_from and value < effective_from:
                raise ValidationError(detail="effective_to must be on or after effective_from")
        return value

class ShiftAssignmentCreate(ShiftAssignmentBase):
    pass

class ShiftAssignmentUpdate(BaseModel):
    pattern_id: Optional[int] = Field(None, description="ID of the shift pattern to update")
    effective_from: Optional[date] = Field(None, description="Date the shift assignment starts to update")
    effective_to: Optional[date] = Field(None, description="Date the shift assignment ends to update")
    is_active: Optional[bool] = Field(None, description="Whether the shift assignment is active to update")

    @field_validator('pattern_id')
    @classmethod
    def validate_pattern_id(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValidationError(detail="Invalid pattern_id")
        return value

    @field_validator('effective_from', 'effective_to')
    @classmethod
    def validate_dates(cls, value: Optional[date], info: ValidationInfo) -> Optional[date]:
        if info.field_name == 'effective_to' and value is not None:
            effective_from = info.data.get('effective_from')
            if effective_from and value < effective_from:
                raise ValidationError(detail="effective_to must be on or after effective_from")
        return value

class ShiftAssignmentOut(ShiftAssignmentBase):
    assignment_id: int = Field(..., description="Unique identifier of the shift assignment")
    created_at: datetime = Field(..., description="Timestamp when the shift assignment was created")
    updated_at: Optional[datetime] = Field(None, description="Timestamp when the shift assignment was last updated")

    @field_validator('assignment_id')
    @classmethod
    def validate_assignment_id(cls, value: int) -> int:
        if value <= 0:
            raise ValidationError(detail="Invalid assignment_id")
        return value

    @field_validator('created_at', 'updated_at')
    @classmethod
    def validate_timezone(cls, value: Optional[datetime], info: ValidationInfo) -> Optional[datetime]:
        if value and value.tzinfo is None:
            raise ValidationError(detail=f"{info.field_name.capitalize()} must include timezone")
        return value

    model_config = ConfigDict(from_attributes=True)