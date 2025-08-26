from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.core.enums import CorrectionStatus
from app.core.exceptions import ValidationError

class TimeCorrectionBase(BaseModel):
    attendance_id: int = Field(..., description="ID of the attendance record to correct")
    original_clock_in: Optional[datetime] = Field(None, description="Original clock-in time")
    original_clock_out: Optional[datetime] = Field(None, description="Original clock-out time")
    corrected_clock_in: Optional[datetime] = Field(None, description="Corrected clock-in time")
    corrected_clock_out: Optional[datetime] = Field(None, description="Corrected clock-out time")
    reason: str = Field(..., description="Reason for the time correction")
    status: CorrectionStatus = Field(CorrectionStatus.DRAFT, description="Status of the correction request")
    approved_by: Optional[int] = Field(None, description="ID of the user who approved/rejected the correction")
    approved_at: Optional[datetime] = Field(None, description="Timestamp when the correction was approved/rejected")
    is_active: bool = Field(True, description="Whether the correction is active")

    @field_validator('attendance_id', 'approved_by')
    @classmethod
    def validate_positive_id(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValidationError(detail=f"Invalid ID: {value}")
        return value

    @field_validator('corrected_clock_in', 'corrected_clock_out')
    @classmethod
    def validate_times(cls, value: Optional[datetime], info) -> Optional[datetime]:
        if value and value.tzinfo is None:
            raise ValidationError(detail=f"{info.field_name} must include timezone")
        return value

class TimeCorrectionCreate(BaseModel):
    attendance_id: int = Field(..., description="ID of the attendance record to correct")
    original_clock_in: Optional[datetime] = Field(None, description="Original clock-in time")
    original_clock_out: Optional[datetime] = Field(None, description="Original clock-out time")
    corrected_clock_in: Optional[datetime] = Field(None, description="Corrected clock-in time")
    corrected_clock_out: Optional[datetime] = Field(None, description="Corrected clock-out time")
    reason: str = Field(..., description="Reason for the time correction")

    @field_validator('attendance_id')
    @classmethod
    def validate_attendance_id(cls, value: int) -> int:
        if value <= 0:
            raise ValidationError(detail="Invalid attendance ID")
        return value

    @field_validator('corrected_clock_in', 'corrected_clock_out')
    @classmethod
    def validate_times(cls, value: Optional[datetime], info) -> Optional[datetime]:
        if value and value.tzinfo is None:
            raise ValidationError(detail=f"{info.field_name} must include timezone")
        return value

class TimeCorrectionUpdate(BaseModel):
    corrected_clock_in: Optional[datetime] = Field(None, description="Updated corrected clock-in time")
    corrected_clock_out: Optional[datetime] = Field(None, description="Updated corrected clock-out time")
    reason: Optional[str] = Field(None, description="Updated reason for the correction")
    status: Optional[CorrectionStatus] = Field(None, description="Updated status of the correction request")
    approved_by: Optional[int] = Field(None, description="Updated ID of the user approving/rejecting")
    approved_at: Optional[datetime] = Field(None, description="Updated timestamp of approval/rejection")
    is_active: Optional[bool] = Field(None, description="Updated active status of the correction")

    @field_validator('approved_by')
    @classmethod
    def validate_approved_by(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValidationError(detail="Invalid approved_by ID")
        return value

    @field_validator('corrected_clock_in', 'corrected_clock_out')
    @classmethod
    def validate_times(cls, value: Optional[datetime], info) -> Optional[datetime]:
        if value and value.tzinfo is None:
            raise ValidationError(detail=f"{info.field_name} must include timezone")
        return value

class TimeCorrectionOut(TimeCorrectionBase):
    correction_id: int = Field(..., description="Unique identifier of the time correction")
    created_at: datetime = Field(..., description="Timestamp when the correction was created")
    updated_at: Optional[datetime] = Field(None, description="Timestamp when the correction was last updated")

    model_config = ConfigDict(from_attributes=True)

class TimeCorrectionApproval(BaseModel):
    status: CorrectionStatus = Field(..., description="Approval status (APPROVED or REJECTED)")

    @field_validator('status')
    @classmethod
    def validate_status(cls, value: CorrectionStatus) -> CorrectionStatus:
        if value not in [CorrectionStatus.APPROVED, CorrectionStatus.REJECTED]:
            raise ValidationError(detail="Status must be 'APPROVED' or 'REJECTED'")
        return value

    model_config = ConfigDict(from_attributes=True)