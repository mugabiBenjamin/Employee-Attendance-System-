from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.permissions import get_user_permissions
from app.core.config import settings
from app.core.enums import Permission
from app.models.users import Users
from app.models.shift_assignments import ShiftAssignments
from app.models.leave_policies import LeavePolicies
from app.core.security import decode_access_token, is_token_blacklisted

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Users:
    try:
        # Check if token is blacklisted
        if await is_token_blacklisted(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is blacklisted",
                headers={"WWW-Authenticate": "Bearer"}
            )

        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        query = select(Users).where(
            Users.user_id == int(user_id),
            Users.is_active == True,
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"}
            )
        return user
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )

async def get_current_active_user(current_user: Users = Depends(get_current_user)) -> Users:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user

async def get_current_admin_user(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Users:
    user_permissions = await get_user_permissions(current_user.user_id, db)
    
    required_admin_perms = [
        Permission.MANAGE_USERS,
        Permission.SYSTEM_CONFIGURATION,
        Permission.MANAGE_DEPARTMENTS
    ]
    
    has_admin_permission = (
        Permission.ALL_PERMISSIONS in user_permissions or
        any(perm in user_permissions for perm in required_admin_perms)
    )
    
    if not has_admin_permission:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current_user

async def get_current_super_admin_user(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Users:
    user_permissions = await get_user_permissions(current_user.user_id, db)
    
    if Permission.ALL_PERMISSIONS not in user_permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current_user

async def get_current_manager_user(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Users:
    user_permissions = await get_user_permissions(current_user.user_id, db)
    
    required_manager_perms = [
        Permission.APPROVE_LEAVE,
        Permission.VIEW_TEAM_ATTENDANCE,
        Permission.GENERATE_REPORTS,
        Permission.MANAGE_OVERTIME
    ]
    
    has_manager_permission = (
        Permission.ALL_PERMISSIONS in user_permissions or
        any(perm in user_permissions for perm in required_manager_perms)
    )
    
    if not has_manager_permission:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current_user

async def get_current_hr_user(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Users:
    user_permissions = await get_user_permissions(current_user.user_id, db)
    
    required_hr_perms = [
        Permission.MANAGE_EMPLOYEES,
        Permission.GENERATE_COMPLIANCE_REPORTS,
        Permission.VIEW_ALL_ATTENDANCE,
        Permission.MANAGE_LEAVE_POLICIES
    ]
    
    has_hr_permission = (
        Permission.ALL_PERMISSIONS in user_permissions or
        any(perm in user_permissions for perm in required_hr_perms)
    )
    
    if not has_hr_permission:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current_user

async def is_manager_or_hr(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> bool:
    user_permissions = await get_user_permissions(current_user.user_id, db)
    
    management_perms = [
        Permission.APPROVE_LEAVE,
        Permission.MANAGE_EMPLOYEES,
        Permission.MANAGE_LEAVE_POLICIES,
        Permission.VIEW_TEAM_ATTENDANCE,
        Permission.ALL_PERMISSIONS
    ]
    
    return any(perm in user_permissions for perm in management_perms)

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
    
    # Check if user has management permissions
    if not await is_manager_or_hr(current_user, db):
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