from typing import Optional, Literal, Dict
from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime, date, time
from zoneinfo import ZoneInfo

class UserBase(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    phone: Optional[str] = None
    employee_type: Literal["full_time", "part_time", "contract", "intern", "temporary"] = "full_time"

    @field_validator("phone")
    def validate_phone(cls, v):
        if v is not None and not v:
            raise ValueError("Phone number cannot be empty if provided")
        import re
        pattern = r'^[\+]?[0-9\s\-\(\)]+$'
        if v is not None and not re.match(pattern, v):
            raise ValueError("Invalid phone number format")
        return v

class UserCreate(UserBase):
    password: str
    hire_date: date
    salary: Optional[float] = None
    manager_id: Optional[int] = None

    @field_validator("password")
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

class UserUpdate(UserBase):
    password: Optional[str] = None
    hire_date: Optional[date] = None
    salary: Optional[float] = None
    manager_id: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("password")
    def validate_password(cls, v):
        if v is not None and len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

class UserOut(UserBase):
    user_id: int
    employee_id: str
    hire_date: date
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class UserAuth(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class DepartmentBase(BaseModel):
    department_name: str
    description: Optional[str] = None
    manager_id: Optional[int] = None
    budget: Optional[float] = None
    location: Optional[str] = None
    is_active: bool = True

class DepartmentCreate(DepartmentBase):
    pass

class DepartmentUpdate(BaseModel):
    department_name: Optional[str] = None
    description: Optional[str] = None
    manager_id: Optional[int] = None
    budget: Optional[float] = None
    location: Optional[str] = None
    is_active: Optional[bool] = None

class DepartmentOut(DepartmentBase):
    department_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class UserDepartmentBase(BaseModel):
    user_id: int
    department_id: int
    is_primary: bool = False

class UserDepartmentCreate(UserDepartmentBase):
    pass

class UserDepartmentUpdate(BaseModel):
    is_primary: Optional[bool] = None

class UserDepartmentOut(UserDepartmentBase):
    user_department_id: int
    assigned_at: datetime

    class Config:
        from_attributes = True

class EmployeeHierarchyBase(BaseModel):
    employee_id: int
    manager_id: int
    level: int = 1
    effective_from: date
    effective_to: Optional[date] = None

class EmployeeHierarchyCreate(EmployeeHierarchyBase):
    pass

class EmployeeHierarchyUpdate(BaseModel):
    level: Optional[int] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None

class EmployeeHierarchyOut(EmployeeHierarchyBase):
    hierarchy_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class ShiftPatternBase(BaseModel):
    pattern_name: str
    shift_type: Literal["morning", "afternoon", "night", "flexible", "split"]
    start_time: time
    end_time: time
    break_duration: int = 0
    is_overnight: bool = False
    is_active: bool = True

class ShiftPatternCreate(ShiftPatternBase):
    pass

class ShiftPatternUpdate(BaseModel):
    pattern_name: Optional[str] = None
    shift_type: Optional[Literal["morning", "afternoon", "night", "flexible", "split"]] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    break_duration: Optional[int] = None
    is_overnight: Optional[bool] = None
    is_active: Optional[bool] = None

class ShiftPatternOut(ShiftPatternBase):
    pattern_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class ShiftAssignmentBase(BaseModel):
    user_id: int
    pattern_id: int
    effective_from: date
    effective_to: Optional[date] = None
    is_active: bool = True

class ShiftAssignmentCreate(ShiftAssignmentBase):
    pass

class ShiftAssignmentUpdate(BaseModel):
    pattern_id: Optional[int] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    is_active: Optional[bool] = None

class ShiftAssignmentOut(ShiftAssignmentBase):
    assignment_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class OvertimeRecordBase(BaseModel):
    attendance_id: int
    user_id: int
    overtime_hours: float
    overtime_rate: float = 1.5
    overtime_amount: Optional[float] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None

class OvertimeRecordCreate(OvertimeRecordBase):
    pass

class OvertimeRecordUpdate(BaseModel):
    overtime_hours: Optional[float] = None
    overtime_rate: Optional[float] = None
    overtime_amount: Optional[float] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None

class OvertimeRecordOut(OvertimeRecordBase):
    overtime_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class TimeCorrectionBase(BaseModel):
    attendance_id: int
    user_id: int
    original_clock_in: Optional[datetime] = None
    original_clock_out: Optional[datetime] = None
    corrected_clock_in: Optional[datetime] = None
    corrected_clock_out: Optional[datetime] = None
    reason: str
    status: Literal["draft", "under_review", "approved", "rejected", "cancelled", "completed"] = "draft"
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None

class TimeCorrectionCreate(TimeCorrectionBase):
    pass

class TimeCorrectionUpdate(BaseModel):
    original_clock_in: Optional[datetime] = None
    original_clock_out: Optional[datetime] = None
    corrected_clock_in: Optional[datetime] = None
    corrected_clock_out: Optional[datetime] = None
    reason: Optional[str] = None
    status: Optional[Literal["draft", "under_review", "approved", "rejected", "cancelled", "completed"]] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None

class TimeCorrectionOut(TimeCorrectionBase):
    correction_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class EmployeeEmergencyContactBase(BaseModel):
    user_id: int
    contact_name: str
    relationship: str
    phone: str
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    is_primary: bool = False

    @field_validator("phone")
    def validate_phone(cls, v):
        import re
        pattern = r'^[\+]?[0-9\s\-\(\)]+$'
        if not re.match(pattern, v):
            raise ValueError("Invalid phone number format")
        return v

class EmployeeEmergencyContactCreate(EmployeeEmergencyContactBase):
    pass

class EmployeeEmergencyContactUpdate(BaseModel):
    contact_name: Optional[str] = None
    relationship: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    is_primary: Optional[bool] = None

    @field_validator("phone")
    def validate_phone(cls, v):
        if v is not None:
            import re
            pattern = r'^[\+]?[0-9\s\-\(\)]+$'
            if not re.match(pattern, v):
                raise ValueError("Invalid phone number format")
        return v

class EmployeeEmergencyContactOut(EmployeeEmergencyContactBase):
    contact_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class SystemLogBase(BaseModel):
    user_id: Optional[int] = None
    action: Literal[
        "INSERT", "UPDATE", "DELETE", "LOGIN", "LOGOUT", "CLOCK_IN", "CLOCK_OUT",
        "password_change", "profile_update", "data_export", "data_import",
        "assign_role", "revoke_role", "view_report", "approve_leave", "reject_leave",
        "create_department", "delete_department"
    ]
    table_affected: Optional[str] = None
    record_id: Optional[int] = None
    old_values: Optional[Dict] = None
    new_values: Optional[Dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

class SystemLogCreate(SystemLogBase):
    pass

class SystemLogUpdate(BaseModel):
    user_id: Optional[int] = None
    action: Optional[Literal[
        "INSERT", "UPDATE", "DELETE", "LOGIN", "LOGOUT", "CLOCK_IN", "CLOCK_OUT",
        "password_change", "profile_update", "data_export", "data_import",
        "assign_role", "revoke_role", "view_report", "approve_leave", "reject_leave",
        "create_department", "delete_department"
    ]] = None
    table_affected: Optional[str] = None
    record_id: Optional[int] = None
    old_values: Optional[Dict] = None
    new_values: Optional[Dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

class SystemLogOut(SystemLogBase):
    log_id: int
    timestamp: datetime

    class Config:
        from_attributes = True