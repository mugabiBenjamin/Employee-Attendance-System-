from typing import Optional, Union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from datetime import datetime, timezone
from app.models.users import Users
from app.models.departments import Departments
from app.models.roles import Roles
from app.models.user_roles import UserRoles
from app.models.user_departments import UserDepartments
from app.models.leave_requests import LeaveRequests
from app.models.leave_policies import LeavePolicies
from app.models.shift_assignments import ShiftAssignments
from app.models.shift_patterns import ShiftPatterns
from app.models.attendance_records import AttendanceRecords
from app.core.enums import LeaveType
from app.core.exceptions import (
    UserNotFoundError,
    DepartmentNotFoundError,
    RoleNotFoundError,
    LeaveRequestNotFoundError,
    LeavePolicyNotFoundError,
    AttendanceRecordNotFoundError,
    ShiftPatternNotFoundError,
    ResourceNotFoundError,
    BusinessLogicError,
)
import logging

logger = logging.getLogger(__name__)

async def validate_user_exists(db: AsyncSession, user_id: int, request_id: Optional[str] = None) -> None:
    """Validate that a user exists and is active."""
    logger.debug(
        f"Validating user existence for user_id: {user_id}",
        extra={"request_id": request_id}
    )
    query = select(Users).where(
        Users.user_id == user_id,
        Users.is_active == True,
        Users.deleted_at == None
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise UserNotFoundError(user_id)

async def validate_department_exists(db: AsyncSession, department_id: int, request_id: Optional[str] = None) -> None:
    """Validate that a department exists and is active."""
    query = select(Departments).where(
        Departments.department_id == department_id,
        Departments.is_active == True,
        Departments.deleted_at == None
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise DepartmentNotFoundError(dept_id=department_id)

async def validate_role_exists(db: AsyncSession, role_id: int, request_id: Optional[str] = None) -> None:
    """Validate that a role exists and is active."""
    query = select(Roles).where(
        Roles.role_id == role_id,
        Roles.is_active == True,
        Roles.deleted_at == None
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise RoleNotFoundError(role_id=role_id)

async def validate_department_not_assigned(
    department_id_or_db: Union[int, AsyncSession],
    db_or_department_id: Union[AsyncSession, int],
    request_id: Optional[str] = None
) -> None:
    """Ensure no active users are assigned to the department. Accepts either (department_id, db) or (db, department_id)."""
    if isinstance(department_id_or_db, AsyncSession):
        db = department_id_or_db
        department_id = int(db_or_department_id)
    else:
        department_id = int(department_id_or_db)
        db = db_or_department_id  # type: ignore[assignment]

    query = select(UserDepartments).where(
        UserDepartments.department_id == department_id,
        UserDepartments.is_active == True,
        UserDepartments.deleted_at == None
    )
    result = await db.execute(query)
    if result.scalars().first():
        raise BusinessLogicError(detail="Cannot delete department with active user assignments")

async def validate_role_not_assigned(
    role_id_or_db: Union[int, AsyncSession],
    db_or_role_id: Union[AsyncSession, int],
    request_id: Optional[str] = None
) -> None:
    """Ensure no active users are assigned to the role. Accepts either (role_id, db) or (db, role_id)."""
    if isinstance(role_id_or_db, AsyncSession):
        db = role_id_or_db
        role_id = int(db_or_role_id)
    else:
        role_id = int(role_id_or_db)
        db = db_or_role_id  # type: ignore[assignment]

    query = select(UserRoles).where(
        UserRoles.role_id == role_id,
        UserRoles.is_active == True,
        UserRoles.deleted_at == None
    )
    result = await db.execute(query)
    if result.scalars().first():
        raise BusinessLogicError(detail="Cannot delete role with active user assignments")

async def validate_leave_request_exists(db: AsyncSession, leave_id: int, request_id: Optional[str] = None) -> None:
    """Validate that a leave request exists and is active."""
    query = select(LeaveRequests).where(
        LeaveRequests.leave_id == leave_id,
        LeaveRequests.is_active == True,
        LeaveRequests.deleted_at == None
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise LeaveRequestNotFoundError(request_id=leave_id)

async def validate_leave_policy_exists(
    db: AsyncSession,
    identifier: Union[int, LeaveType],
    request_id: Optional[str] = None
) -> None:
    """Validate that a leave policy exists.

    - If identifier is an int, validates by policy_id
    - If identifier is a LeaveType, validates there is an active policy for that type (by date window)
    """
    if isinstance(identifier, int):
        query = select(LeavePolicies).where(
            LeavePolicies.policy_id == identifier,
            LeavePolicies.is_active == True,
            LeavePolicies.deleted_at == None
        )
    else:
        today = datetime.now(timezone.utc).date()
        query = select(LeavePolicies).where(
            LeavePolicies.leave_type == identifier,
            LeavePolicies.is_active == True,
            LeavePolicies.deleted_at == None,
            LeavePolicies.effective_from <= today,
            or_(LeavePolicies.effective_to.is_(None), LeavePolicies.effective_to >= today)
        )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        # For type-based validation, raise without id; for id-based, include id
        if isinstance(identifier, int):
            raise LeavePolicyNotFoundError(policy_id=identifier)
        raise LeavePolicyNotFoundError()

async def validate_shift_assignment_exists(db: AsyncSession, assignment_id: int, request_id: Optional[str] = None) -> None:
    """Validate that a shift assignment exists and is active."""
    query = select(ShiftAssignments).where(
        ShiftAssignments.assignment_id == assignment_id,
        ShiftAssignments.is_active == True,
        ShiftAssignments.deleted_at == None
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise ResourceNotFoundError(resource="ShiftAssignment", identifier=assignment_id)

async def validate_shift_pattern_exists(db: AsyncSession, pattern_id: int, request_id: Optional[str] = None) -> None:
    """Validate that a shift pattern exists and is active."""
    query = select(ShiftPatterns).where(
        ShiftPatterns.pattern_id == pattern_id,
        ShiftPatterns.is_active == True,
        ShiftPatterns.deleted_at == None
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise ShiftPatternNotFoundError(pattern_id=pattern_id)

async def validate_attendance_record_exists(db: AsyncSession, attendance_id: int, request_id: Optional[str] = None) -> None:
    """Validate that an attendance record exists and is active."""
    query = select(AttendanceRecords).where(
        AttendanceRecords.attendance_id == attendance_id,
        AttendanceRecords.is_active == True,
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise AttendanceRecordNotFoundError(record_id=attendance_id)