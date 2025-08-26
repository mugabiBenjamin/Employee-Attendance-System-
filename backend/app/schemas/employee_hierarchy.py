from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.core.exceptions import ValidationError

class EmployeeHierarchyBase(BaseModel):
    employee_id: int = Field(..., description="ID of the employee")
    supervisor_id: int = Field(..., description="ID of the manager")
    level: int = Field(1, ge=1, le=10, description="Hierarchy level (1-10)")
    effective_from: date = Field(..., description="Effective start date")
    effective_to: Optional[date] = Field(None, description="Effective end date")
    is_active: bool = Field(True, description="Whether the hierarchy is active")

    @field_validator('employee_id', 'supervisor_id')
    @classmethod
    def validate_ids(cls, value: int, info) -> int:
        if value <= 0:
            raise ValidationError(detail=f"Invalid {info.field_name}")
        return value

    @field_validator('supervisor_id')
    @classmethod
    def prevent_self_reporting(cls, value: int, values) -> int:
        if 'employee_id' in values and value == values['employee_id']:
            raise ValidationError(detail="Employee cannot be their own manager")
        return value

    @field_validator('effective_from')
    @classmethod
    def validate_effective_from(cls, value: date) -> date:
        if value > date.today():
            raise ValidationError(detail="Effective from date cannot be in the future")
        return value

    @field_validator('effective_to')
    @classmethod
    def validate_effective_to(cls, value: Optional[date], values) -> Optional[date]:
        if value and 'effective_from' in values and value < values['effective_from']:
            raise ValidationError(detail="Effective to date must be on or after effective from date")
        return value

class EmployeeHierarchyCreate(EmployeeHierarchyBase):
    employee_id: int
    supervisor_id: int
    level: Optional[int] = Field(1, ge=1, le=10)

class EmployeeHierarchyUpdate(BaseModel):
    supervisor_id: Optional[int] = Field(None, description="Updated manager ID")
    level: Optional[int] = Field(None, ge=1, le=10, description="Updated hierarchy level")
    effective_from: Optional[date] = Field(None, description="Updated effective start date")
    effective_to: Optional[date] = Field(None, description="Updated effective end date")
    is_active: Optional[bool] = Field(None, description="Updated active status")

    @field_validator('supervisor_id')
    @classmethod
    def validate_supervisor_id(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValidationError(detail="Invalid manager ID")
        return value

    @field_validator('effective_from')
    @classmethod
    def validate_effective_from(cls, value: Optional[date]) -> Optional[date]:
        if value and value > date.today():
            raise ValidationError(detail="Effective from date cannot be in the future")
        return value

    @field_validator('effective_to')
    @classmethod
    def validate_effective_to(cls, value: Optional[date], values) -> Optional[date]:
        if value and 'effective_from' in values and values['effective_from'] and value < values['effective_from']:
            raise ValidationError(detail="Effective to date must be on or after effective from date")
        return value

class EmployeeHierarchyOut(EmployeeHierarchyBase):
    hierarchy_id: int = Field(..., description="Unique identifier of the hierarchy")
    created_at: datetime = Field(..., description="Timestamp when the hierarchy was created")
    updated_at: Optional[datetime] = Field(None, description="Timestamp when the hierarchy was last updated")

    @field_validator('created_at', 'updated_at')
    @classmethod
    def validate_timezone(cls, value: Optional[datetime], info) -> Optional[datetime]:
        if value and value.tzinfo is None:
            raise ValidationError(detail=f"{info.field_name} must include timezone")
        return value

    model_config = ConfigDict(from_attributes=True)