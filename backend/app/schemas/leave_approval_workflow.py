from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.core.enums import LeaveRequestStatus, LeaveType
from app.core.exceptions import ValidationError

class LeaveApprovalWorkflowBase(BaseModel):
    leave_id: int
    approver_id: int
    level: int = Field(..., ge=1, le=5)
    status: LeaveRequestStatus = LeaveRequestStatus.UNDER_REVIEW
    comments: Optional[str] = None
    action_taken_at: Optional[datetime] = None
    is_active: bool = True

    @field_validator('leave_id', 'approver_id')
    @classmethod
    def validate_ids(cls, value: int, info: dict) -> int:
        if value <= 0:
            field = info.field_name
            raise ValidationError(detail=f"Invalid {field}")
        return value

    @field_validator('action_taken_at')
    @classmethod
    def validate_timezone(cls, value: Optional[datetime], info: dict) -> Optional[datetime]:
        if value and value.tzinfo is None:
            raise ValidationError(detail=f"{info.field_name.capitalize()} must include timezone")
        if value and value > datetime.now(timezone.utc):
            raise ValidationError(detail=f"{info.field_name.capitalize()} cannot be in the future")
        return value

class LeaveApprovalWorkflowCreate(LeaveApprovalWorkflowBase):
    leave_id: int
    approver_id: int
    status: LeaveRequestStatus
    comments: Optional[str] = None
    level: int = Field(..., ge=1, le=5)

class LeaveApprovalWorkflowUpdate(BaseModel):
    status: Optional[LeaveRequestStatus] = None
    comments: Optional[str] = None
    action_taken_at: Optional[datetime] = None
    is_active: Optional[bool] = None

    @field_validator('action_taken_at')
    @classmethod
    def validate_timezone(cls, value: Optional[datetime], info: dict) -> Optional[datetime]:
        if value and value.tzinfo is None:
            raise ValidationError(detail=f"{info.field_name.capitalize()} must include timezone")
        if value and value > datetime.now(timezone.utc):
            raise ValidationError(detail=f"{info.field_name.capitalize()} cannot be in the future")
        return value

class LeaveApprovalWorkflowOut(LeaveApprovalWorkflowBase):
    workflow_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_validator('workflow_id')
    @classmethod
    def validate_workflow_id(cls, value: int) -> int:
        if value <= 0:
            raise ValidationError(detail="Invalid workflow_id")
        return value

    @field_validator('created_at', 'updated_at')
    @classmethod
    def validate_timezone(cls, value: Optional[datetime], info: dict) -> Optional[datetime]:
        if value and value.tzinfo is None:
            raise ValidationError(detail=f"{info.field_name.capitalize()} must include timezone")
        return value

    model_config = ConfigDict(from_attributes=True)

class WorkflowStepCreate(BaseModel):
    leave_id: int
    approver_id: int
    level: int = Field(..., ge=1, le=5)

    @field_validator('leave_id', 'approver_id')
    @classmethod
    def validate_ids(cls, value: int, info: dict) -> int:
        if value <= 0:
            field = info.field_name
            raise ValidationError(detail=f"Invalid {field}")
        return value

    model_config = ConfigDict(from_attributes=True)

class WorkflowStepOut(LeaveApprovalWorkflowOut):
    pass

class WorkflowByTypeQuery(BaseModel):
    leave_type: LeaveType