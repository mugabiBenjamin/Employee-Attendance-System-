from typing import AsyncGenerator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.users import Users
from app.models.user_roles import UserRoles, Roles
from app.models.shift_assignments import ShiftAssignment
from app.models.leave import LeavePolicy
from app.core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token")

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_db() as session:
        yield session

async def get_current_active_user(current_user: Users = Depends(get_current_user)) -> Users:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user

async def get_current_admin_user(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
) -> Users:
    query = select(Users).join(UserRoles).join(Roles).where(
        Users.user_id == current_user.user_id,
        (Roles.role_name.in_(["Admin", "Super_Admin"]) | 
         Roles.permissions.contains('{"manage_users": true}') |
         Roles.permissions.contains('{"system_configuration": true}') |
         Roles.permissions.contains('{"view_logs": true}') |
         Roles.permissions.contains('{"manage_departments": true}'))
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current_user

async def get_current_super_admin_user(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
) -> Users:
    query = select(Users).join(UserRoles).join(Roles).where(
        Users.user_id == current_user.user_id,
        (Roles.role_name == "Super_Admin" | 
         Roles.permissions.contains('{"all_permissions": true}'))
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current_user

async def get_current_manager_user(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
) -> Users:
    query = select(Users).join(UserRoles).join(Roles).where(
        Users.user_id == current_user.user_id,
        (Roles.role_name == "Manager" | 
         Roles.permissions.contains('{"approve_leave": true}') |
         Roles.permissions.contains('{"view_team_attendance": true}') |
         Roles.permissions.contains('{"generate_reports": true}') |
         Roles.permissions.contains('{"manage_overtime": true}'))
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current_user

async def get_current_hr_user(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
) -> Users:
    query = select(Users).join(UserRoles).join(Roles).where(
        Users.user_id == current_user.user_id,
        (Roles.role_name == "HR" | 
         Roles.permissions.contains('{"manage_employees": true}') |
         Roles.permissions.contains('{"generate_compliance_reports": true}') |
         Roles.permissions.contains('{"view_all_attendance": true}') |
         Roles.permissions.contains('{"manage_leave_policies": true}'))
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current_user

async def is_manager_or_hr(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
) -> bool:
    query = select(Users).join(UserRoles).join(Roles).where(
        Users.user_id == current_user.user_id,
        (Roles.role_name.in_(["Manager", "HR", "Admin", "Super_Admin"]) |
         Roles.permissions.contains('{"approve_leave": true}') |
         Roles.permissions.contains('{"manage_employees": true}') |
         Roles.permissions.contains('{"manage_leave_policies": true}') |
         Roles.permissions.contains('{"manage_shifts": true}'))
    )
    result = await db.execute(query)
    return result.first() is not None

async def validate_shift_or_leave(
    shift_assignment: Optional[ShiftAssignment] = None,
    leave_policy: Optional[LeavePolicy] = None,
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
) -> None:
    if not shift_assignment and not leave_policy:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either shift_assignment or leave_policy must be provided"
        )
    
    has_permission = await is_manager_or_hr(current_user, db)
    if not has_permission:
        query = select(Users).join(UserRoles).join(Roles).where(
            Users.user_id == current_user.user_id,
            (Roles.permissions.contains('{"manage_shifts": true}') |
             Roles.permissions.contains('{"manage_leave_policies": true}'))
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to manage shifts or leave policies"
            )
    
    if shift_assignment:
        query = select(ShiftAssignment).where(
            ShiftAssignment.assignment_id == shift_assignment.assignment_id,
            ShiftAssignment.is_active == True
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shift assignment not found or inactive"
            )
    
    if leave_policy:
        query = select(LeavePolicy).where(
            LeavePolicy.policy_id == leave_policy.policy_id,
            LeavePolicy.effective_to.is_(None) | (LeavePolicy.effective_to >= func.current_date())
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Leave policy not found or expired"
            )