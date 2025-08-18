from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.core.enums import LeaveRequestStatus

class LeaveApprovalWorkflowBase(BaseModel):
    leave_id: int
    approver_id: int
    level: int = Field(..., ge=1, le=5)
    status: LeaveRequestStatus = LeaveRequestStatus.UNDER_REVIEW
    comments: Optional[str] = None
    action_taken_at: Optional[datetime] = None
    is_active: bool = True

class LeaveApprovalWorkflowCreate(LeaveApprovalWorkflowBase):
    request_id: int = Field(..., alias="request_id")
    approver_id: int
    status: LeaveRequestStatus
    comments: Optional[str] = None
    level: int = Field(..., ge=1, le=5)

class LeaveApprovalWorkflowUpdate(BaseModel):
    status: Optional[LeaveRequestStatus] = None
    comments: Optional[str] = None
    action_taken_at: Optional[datetime] = None
    is_active: Optional[bool] = None

class LeaveApprovalWorkflowOut(LeaveApprovalWorkflowBase):
    workflow_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class WorkflowStepCreate(BaseModel):
    request_id: int
    approver_id: int
    level: int = Field(..., ge=1, le=5)
    
    model_config = ConfigDict(from_attributes=True)

class WorkflowStepOut(LeaveApprovalWorkflowOut):
    pass