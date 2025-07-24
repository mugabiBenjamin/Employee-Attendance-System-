
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class LeaveApprovalWorkflowBase(BaseModel):
    leave_id: int
    approver_id: int
    level: int = Field(..., ge=1, le=5)
    status: str = 'under_review'
    comments: Optional[str] = None
    action_taken_at: Optional[datetime] = None

class LeaveApprovalWorkflowCreate(LeaveApprovalWorkflowBase):
    pass

class LeaveApprovalWorkflowUpdate(BaseModel):
    status: Optional[str] = None
    comments: Optional[str] = None
    action_taken_at: Optional[datetime] = None

class LeaveApprovalWorkflowOut(LeaveApprovalWorkflowBase):
    workflow_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True