from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.core.enums import LeaveRequestStatus

class LeaveApprovalWorkflowBase(BaseModel):
    leave_id: int
    approver_id: int
    level: int = Field(..., ge=1, le=5)
    status: str = 'under_review'
    comments: Optional[str] = None
    action_taken_at: Optional[datetime] = None

class LeaveApprovalWorkflowCreate(LeaveApprovalWorkflowBase):
    request_id: int
    approver_id: int
    status: LeaveRequestStatus
    comments: Optional[str] = None

class LeaveApprovalWorkflowUpdate(BaseModel):
    status: Optional[str] = None
    comments: Optional[str] = None
    action_taken_at: Optional[datetime] = None

class LeaveApprovalWorkflowOut(LeaveApprovalWorkflowBase):
    workflow_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)