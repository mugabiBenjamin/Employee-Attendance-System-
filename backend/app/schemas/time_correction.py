from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.core.enums import CorrectionStatus

class TimeCorrectionBase(BaseModel):
    attendance_id: int = Field(..., description="ID of the attendance record to correct")
    user_id: int = Field(..., description="ID of the user requesting the correction")
    original_clock_in: Optional[datetime] = Field(None, description="Original clock-in time")
    original_clock_out: Optional[datetime] = Field(None, description="Original clock-out time")
    corrected_clock_in: Optional[datetime] = Field(None, description="Corrected clock-in time")
    corrected_clock_out: Optional[datetime] = Field(None, description="Corrected clock-out time")
    reason: str = Field(..., description="Reason for the time correction")
    status: CorrectionStatus = Field(CorrectionStatus.DRAFT, description="Status of the correction request")
    approved_by: Optional[int] = Field(None, description="ID of the user who approved/rejected the correction")
    approved_at: Optional[datetime] = Field(None, description="Timestamp when the correction was approved/rejected")

class TimeCorrectionCreate(TimeCorrectionBase):
    pass

class TimeCorrectionUpdate(BaseModel):
    corrected_clock_in: Optional[datetime] = Field(None, description="Updated corrected clock-in time")
    corrected_clock_out: Optional[datetime] = Field(None, description="Updated corrected clock-out time")
    reason: Optional[str] = Field(None, description="Updated reason for the correction")
    status: Optional[CorrectionStatus] = Field(None, description="Updated status of the correction request")
    approved_by: Optional[int] = Field(None, description="Updated ID of the user approving/rejecting")
    approved_at: Optional[datetime] = Field(None, description="Updated timestamp of approval/rejection")

class TimeCorrectionOut(TimeCorrectionBase):
    correction_id: int = Field(..., description="Unique identifier of the time correction")
    created_at: datetime = Field(..., description="Timestamp when the correction was created")
    updated_at: Optional[datetime] = Field(None, description="Timestamp when the correction was last updated")

    model_config = ConfigDict(from_attributes=True)

class TimeCorrectionApproval(BaseModel):
    status: CorrectionStatus = Field(..., description="Approval status (APPROVED or REJECTED)")

    model_config = ConfigDict(from_attributes=True)