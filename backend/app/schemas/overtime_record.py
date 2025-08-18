from datetime import datetime, date, timezone
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.core.enums import OvertimeStatus
from app.core.exceptions import ValidationError

class OvertimeRecordBase(BaseModel):
    user_id: int
    date: date
    overtime_hours: float = Field(..., gt=0)
    overtime_rate: float = Field(1.5, gt=0)
    overtime_amount: Optional[float] = None
    description: Optional[str] = None
    status: OvertimeStatus = OvertimeStatus.PENDING
    comments: Optional[str] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    is_active: bool = True

    @field_validator('date')
    @classmethod
    def validate_date(cls, value):
        if value > datetime.now(timezone.utc).date():
            raise ValidationError(detail="Date cannot be in the future.")
        return value

    @field_validator('overtime_amount')
    @classmethod
    def validate_overtime_amount(cls, amount, info):
        if amount is not None and 'overtime_hours' in info.data and 'overtime_rate' in info.data:
            expected_amount = info.data['overtime_hours'] * info.data['overtime_rate']
            if round(amount, 2) != round(expected_amount, 2):
                raise ValidationError(detail="overtime_amount must equal overtime_hours * overtime_rate")
        return amount or (info.data['overtime_hours'] * info.data['overtime_rate'] if 'overtime_hours' in info.data and 'overtime_rate' in info.data else None)

class OvertimeRecordCreate(OvertimeRecordBase):
    user_id: int
    date: date
    overtime_hours: float
    description: Optional[str] = None

class OvertimeRecordUpdate(BaseModel):
    overtime_hours: Optional[float] = Field(None, gt=0)
    overtime_rate: Optional[float] = Field(None, gt=0)
    overtime_amount: Optional[float] = None
    description: Optional[str] = None
    status: Optional[OvertimeStatus] = None
    comments: Optional[str] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    is_active: Optional[bool] = None

    @field_validator('date')
    @classmethod
    def validate_date(cls, value):
        if value and value > datetime.now(timezone.utc).date():
            raise ValidationError(detail="Date cannot be in the future.")
        return value

    @field_validator('overtime_amount')
    @classmethod
    def validate_overtime_amount(cls, amount, info):
        if amount is not None and 'overtime_hours' in info.data and 'overtime_rate' in info.data:
            expected_amount = info.data['overtime_hours'] * info.data['overtime_rate']
            if round(amount, 2) != round(expected_amount, 2):
                raise ValidationError(detail="overtime_amount must equal overtime_hours * overtime_rate")
        return amount

class OvertimeRecordOut(OvertimeRecordBase):
    overtime_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class OvertimeRecordApproval(BaseModel):
    status: OvertimeStatus
    comments: Optional[str] = None