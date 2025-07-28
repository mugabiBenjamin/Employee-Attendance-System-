from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.permissions import check_permissions
from app.core.config import settings
from app.core.enums import Permission
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.models.shift_assignments import ShiftAssignments
from app.models.leave_policies import LeavePolicies
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from app.models.users import Users
from app.models.shift_assignments import ShiftAssignments
from app.models.leave_policies import LeavePolicies

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token")

class UserOut(BaseModel):
    user_id: int
    email: str
    first_name: str
    last_name: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Users:
    # Placeholder for actual token validation logic
    # This should include JWT decoding and user lookup
    query = select(Users).where(Users.is_active == True)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return user

async def get_current_active_user(current_user: Users = Depends(get_current_user)) -> Users:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user

async def get_current_admin_user(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Users:
    query = select(Users).join(UserRoles).join(Roles).where(
        Users.user_id == current_user.user_id,
        UserRoles.is_active == True,
        Roles.is_active == True,
        (Roles.role_name.in_(["Admin", "Super_Admin"]) | 
         Roles.permissions.contains('{"manage_users": true}') |
         Roles.permissions.contains('{"system_configuration": true}') |
         Roles.permissions.contains('{"manage_departments": true}'))
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current_user

async def get_current_super_admin_user(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Users:
    query = select(Users).join(UserRoles).join(Roles).where(
        Users.user_id == current_user.user_id,
        UserRoles.is_active == True,
        Roles.is_active == True,
        (Roles.role_name == "Super_Admin" | 
         Roles.permissions.contains('{"all_permissions": true}'))
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current_user

async def get_current_manager_user(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Users:
    query = select(Users).join(UserRoles).join(Roles).where(
        Users.user_id == current_user.user_id,
        UserRoles.is_active == True,
        Roles.is_active == True,
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
    db: AsyncSession = Depends(get_db)
) -> Users:
    query = select(Users).join(UserRoles).join(Roles).where(
        Users.user_id == current_user.user_id,
        UserRoles.is_active == True,
        Roles.is_active == True,
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
    db: AsyncSession = Depends(get_db)
) -> bool:
    query = select(Users).join(UserRoles).join(Roles).where(
        Users.user_id == current_user.user_id,
        UserRoles.is_active == True,
        Roles.is_active == True,
        (Roles.role_name.in_(["Manager", "HR", "Admin", "Super_Admin"]) |
         Roles.permissions.contains('{"approve_leave": true}') |
         Roles.permissions.contains('{"manage_employees": true}') |
         Roles.permissions.contains('{"manage_leave_policies": true}') |
         Roles.permissions.contains('{"manage_shift_assignments": true}')))
    result = await db.execute(query)
    return result.first() is not None

async def validate_shift_or_leave(
    shift_assignment: Optional[ShiftAssignments] = None,
    leave_policy: Optional[LeavePolicies] = None,
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> None:
    if not shift_assignment and not leave_policy:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either shift_assignment or leave_policy must be provided"
        )
    
    has_permission = await check_permissions([Permission.MANAGE_SHIFT_ASSIGNMENTS.value, Permission.MANAGE_LEAVE_POLICIES.value], current_user, db)
    if not has_permission and not await is_manager_or_hr(current_user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to manage shifts or leave policies"
        )
    
    if shift_assignment:
        query = select(ShiftAssignments).where(
            ShiftAssignments.assignment_id == shift_assignment.assignment_id,
            ShiftAssignments.is_active == True
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shift assignment not found or inactive"
            )
    
    if leave_policy:
        query = select(LeavePolicies).where(
            LeavePolicies.policy_id == leave_policy.policy_id,
            (LeavePolicies.effective_to.is_(None) | (LeavePolicies.effective_to >= func.current_date()))
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Leave policy not found or expired"
            )