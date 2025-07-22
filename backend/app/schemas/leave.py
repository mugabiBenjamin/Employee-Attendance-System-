from typing import Optional, Literal
from pydantic import BaseModel
from datetime import datetime, date
from zoneinfo import ZoneInfo

class LeaveRequestBase(BaseModel):
    user_id: int
    leave_type: Literal[
        "annual", "sick", "maternity", "paternity", "emergency", "unpaid",
        "casual", "compensatory", "bereavement", "leave_of_absence", "public_holiday"
    ]
    start_date: date
    end_date: date
    days_requested: int
    reason: Optional[str] = None
    status: Literal["draft", "under_review", "approved", "rejected", "cancelled", "completed"] = "draft"
    attachment_url: Optional[str] = None

class LeaveRequestCreate(LeaveRequestBase):
    pass

class LeaveRequestUpdate(BaseModel):
    leave_type: Optional[Literal[
        "annual", "sick", "maternity", "paternity", "emergency", "unpaid",
        "casual", "compensatory", "bereavement", "leave_of_absence", "public_holiday"
    ]] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    days_requested: Optional[int] = None
    reason: Optional[str] = None
    status: Optional[Literal["draft", "under_review", "approved", "rejected", "cancelled", "completed"]] = None
    comments: Optional[str] = None
    attachment_url: Optional[str] = None

class LeaveRequestOut(LeaveRequestBase):
    leave_id: int
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    comments: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class LeaveBalanceBase(BaseModel):
    user_id: int
    leave_type: Literal[
        "annual", "sick", "maternity", "paternity", "emergency", "unpaid",
        "casual", "compensatory", "bereavement", "leave_of_absence", "public_holiday"
    ]
    allocated_days: int = 0
    used_days: int = 0
    carried_forward: int = 0
    year: int

class LeaveBalanceCreate(LeaveBalanceBase):
    pass

class LeaveBalanceUpdate(BaseModel):
    allocated_days: Optional[int] = None
    used_days: Optional[int] = None
    carried_forward: Optional[int] = None
    year: Optional[int] = None

class LeaveBalanceOut(LeaveBalanceBase):
    balance_id: int
    updated_at: datetime

    class Config:
        from_attributes = True

class LeavePolicyBase(BaseModel):
    employee_type: Literal["full_time", "part_time", "contract", "intern", "temporary"]
    leave_type: Literal[
        "annual", "sick", "maternity", "paternity", "emergency", "unpaid",
        "casual", "compensatory", "bereavement", "leave_of_absence", "public_holiday"
    ]
    annual_allocation: int = 0
    carry_forward_limit: int = 0
    max_consecutive_days: Optional[int] = None
    requires_approval: bool = True
    approval_levels: int = 1
    accrual_rate: float = 0.0
    effective_from: date
    effective_to: Optional[date] = None

class LeavePolicyCreate(LeavePolicyBase):
    pass

class LeavePolicyUpdate(BaseModel):
    employee_type: Optional[Literal["full_time", "part_time", "contract", "intern", "temporary"]] = None
    leave_type: Optional[Literal[
        "annual", "sick", "maternity", "paternity", "emergency", "unpaid",
        "casual", "compensatory", "bereavement", "leave_of_absence", "public_holiday"
    ]] = None
    annual_allocation: Optional[int] = None
    carry_forward_limit: Optional[int] = None
    max_consecutive_days: Optional[int] = None
    requires_approval: Optional[bool] = None
    approval_levels: Optional[int] = None
    accrual_rate: Optional[float] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None

class LeavePolicyOut(LeavePolicyBase):
    policy_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class LeaveApprovalWorkflowBase(BaseModel):
    leave_id: int
    approver_id: int
    level: int
    status: Literal["draft", "under_review", "approved", "rejected", "cancelled", "completed"] = "under_review"
    comments: Optional[str] = None
    action_taken_at: Optional[datetime] = None

class LeaveApprovalWorkflowCreate(LeaveApprovalWorkflowBase):
    pass

class LeaveApprovalWorkflowUpdate(BaseModel):
    status: Optional[Literal["draft", "under_review", "approved", "rejected", "cancelled", "completed"]] = None
    comments: Optional[str] = None
    action_taken_at: Optional[datetime] = None

class LeaveApprovalWorkflowOut(LeaveApprovalWorkflowBase):
    workflow_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class HolidayCalendarBase(BaseModel):
    holiday_name: str
    holiday_date: date
    is_recurring: bool = False
    applies_to_all: bool = True
    department_id: Optional[int] = None
    year: int

class HolidayCalendarCreate(HolidayCalendarBase):
    pass

class HolidayCalendarUpdate(BaseModel):
    holiday_name: Optional[str] = None
    holiday_date: Optional[date] = None
    is_recurring: Optional[bool] = None
    applies_to_all: Optional[bool] = None
    department_id: Optional[int] = None
    year: Optional[int] = None

class HolidayCalendarOut(HolidayCalendarBase):
    holiday_id: int
    created_at: datetime

    class Config:
        from_attributes = True