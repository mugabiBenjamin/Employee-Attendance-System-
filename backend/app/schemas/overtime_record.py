from datetime import datetime, date as DateType, timezone
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator, ValidationInfo
from app.core.enums import OvertimeStatus
from app.core.exceptions import ValidationError

class OvertimeRecordBase(BaseModel):
    user_id: int = Field(..., description="ID of the user")
    attendance_id: int = Field(..., description="ID of the associated attendance record")
    date: DateType = Field(..., description="Date of the overtime")
    overtime_hours: float = Field(..., gt=0, description="Overtime hours worked")
    overtime_rate: float = Field(1.5, gt=0, description="Overtime pay rate multiplier")
    overtime_amount: Optional[float] = Field(None, description="Calculated overtime amount")
    description: Optional[str] = Field(None, max_length=255, description="Description of the overtime")
    status: OvertimeStatus = Field(OvertimeStatus.PENDING, description="Status of the overtime record")
    comments: Optional[str] = Field(None, max_length=255, description="Approval or rejection comments")
    approved_by: Optional[int] = Field(None, description="ID of the approving user")
    approved_at: Optional[datetime] = Field(None, description="Timestamp of approval")
    is_active: bool = Field(True, description="Whether the record is active")

    @field_validator('user_id', 'approved_by', 'attendance_id')
    @classmethod
    def validate_ids(cls, value: Optional[int], info: ValidationInfo) -> Optional[int]:
        if value is not None and value <= 0:
            field = info.field_name
            raise ValidationError(detail=f"Invalid {field}")
        return value

    @field_validator('date')
    @classmethod
    def validate_date(cls, value: DateType) -> DateType:
        if value > datetime.now(timezone.utc).date():
            raise ValidationError(detail="Date cannot be in the future")
        return value

    @field_validator('approved_at')
    @classmethod
    def validate_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value and value.tzinfo is None:
            raise ValidationError(detail="Approved_at must include timezone")
        return value

    @field_validator('overtime_amount')
    @classmethod
    def validate_overtime_amount(cls, value: Optional[float], info: ValidationInfo) -> Optional[float]:
        hours = info.data.get('overtime_hours')
        rate = info.data.get('overtime_rate')
        if value is not None and isinstance(hours, (int, float)) and isinstance(rate, (int, float)):
            expected_amount = hours * rate
            if round(value, 2) != round(expected_amount, 2):
                raise ValidationError(detail="overtime_amount must equal overtime_hours * overtime_rate")
        return value

class OvertimeRecordCreate(OvertimeRecordBase):
    user_id: int
    attendance_id: int
    date: DateType
    overtime_hours: float
    description: Optional[str] = None

class OvertimeRecordUpdate(BaseModel):
    user_id: Optional[int] = Field(None, description="Updated user ID")
    attendance_id: Optional[int] = Field(None, description="Updated attendance record ID")
    date: Optional[DateType] = Field(None, description="Updated date of the overtime")
    overtime_hours: Optional[float] = Field(None, gt=0, description="Updated overtime hours")
    overtime_rate: Optional[float] = Field(None, gt=0, description="Updated overtime rate")
    overtime_amount: Optional[float] = Field(None, description="Updated overtime amount")
    description: Optional[str] = Field(None, max_length=255, description="Updated description")
    status: Optional[OvertimeStatus] = Field(None, description="Updated status")
    comments: Optional[str] = Field(None, max_length=255, description="Updated comments")
    approved_by: Optional[int] = Field(None, description="Updated approver ID")
    approved_at: Optional[datetime] = Field(None, description="Updated approval timestamp")
    is_active: Optional[bool] = Field(None, description="Updated active status")

    @field_validator('user_id', 'approved_by', 'attendance_id')
    @classmethod
    def validate_ids(cls, value: Optional[int], info: ValidationInfo) -> Optional[int]:
        if value is not None and value <= 0:
            field = info.field_name
            raise ValidationError(detail=f"Invalid {field}")
        return value

    @field_validator('date')
    @classmethod
    def validate_date(cls, value: Optional[DateType]) -> Optional[DateType]:
        if value and value > datetime.now(timezone.utc).date():
            raise ValidationError(detail="Date cannot be in the future")
        return value

    @field_validator('approved_at')
    @classmethod
    def validate_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value and value.tzinfo is None:
            raise ValidationError(detail="Approved_at must include timezone")
        return value

    @field_validator('overtime_amount')
    @classmethod
    def validate_overtime_amount(cls, value: Optional[float], info: ValidationInfo) -> Optional[float]:
        hours = info.data.get('overtime_hours')
        rate = info.data.get('overtime_rate')
        if value is not None and isinstance(hours, (int, float)) and isinstance(rate, (int, float)):
            expected_amount = hours * rate
            if round(value, 2) != round(expected_amount, 2):
                raise ValidationError(detail="overtime_amount must equal overtime_hours * overtime_rate")
        return value

class OvertimeRecordOut(OvertimeRecordBase):
    overtime_id: int = Field(..., description="Unique identifier of the overtime record")
    created_at: datetime = Field(..., description="Timestamp when the record was created")
    updated_at: Optional[datetime] = Field(None, description="Timestamp when the record was last updated")

    @field_validator('created_at', 'updated_at')
    @classmethod
    def validate_timezone(cls, value: Optional[datetime], info: ValidationInfo) -> Optional[datetime]:
        if value and value.tzinfo is None:
            raise ValidationError(detail=f"{info.field_name.capitalize()} must include timezone")
        return value

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()}
    )

class OvertimeRecordApproval(BaseModel):
    status: OvertimeStatus = Field(..., description="Approval status")
    comments: Optional[str] = Field(None, max_length=255, description="Approval or rejection comments")