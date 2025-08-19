from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, get_cache, set_cache
from app.core.permissions import get_user_permissions
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.models.users import Users
from app.models.shift_assignments import ShiftAssignments
from app.models.leave_policies import LeavePolicies
from app.core.security import decode_access_token, is_token_blacklisted
from app.core.mail import send_email
from app.core.exceptions import ValidationError
import logging

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{get_settings().API_V1_STR}/auth/token")

def get_request_id(request: Request) -> Optional[str]:
    """Extract request_id from the request state."""
    return request.state.request_id if hasattr(request.state, "request_id") else None

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id)
) -> Users:
    """Authenticate and retrieve the current user from a JWT token."""
    try:
        if await is_token_blacklisted(token):
            logger.error(f"Blacklisted token attempted access", extra={"request_id": request_id})
            await notify_admins(token, db, settings, request_id, "Blacklisted token attempted access")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is blacklisted",
                headers={"WWW-Authenticate": "Bearer"}
            )

        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            logger.error(f"Invalid token: No user ID in payload", extra={"request_id": request_id})
            await notify_admins(token, db, settings, request_id, "Invalid token: No user ID")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: No user ID in payload",
                headers={"WWW-Authenticate": "Bearer"}
            )

        try:
            user_id_int = int(user_id)
            if user_id_int <= 0:
                raise ValidationError(detail="Invalid user_id")
        except ValueError:
            logger.error(f"Invalid user_id format: {user_id}", extra={"request_id": request_id})
            await notify_admins(token, db, settings, request_id, f"Invalid user_id format: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: Invalid user ID format",
                headers={"WWW-Authenticate": "Bearer"}
            )

        query = select(Users).where(
            Users.user_id == user_id_int,
            Users.is_active == True,
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            logger.error(f"User not found or inactive: {user_id}", extra={"request_id": request_id})
            await notify_admins(token, db, settings, request_id, f"User not found or inactive: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
                headers={"WWW-Authenticate": "Bearer"}
            )

        user.last_login = func.current_timestamp()
        user.updated_at = func.current_timestamp()
        db.add(user)
        await db.commit()
        await db.refresh(user)

        logger.info(
            f"User authenticated, user_id: {user.user_id}",
            extra={"request_id": request_id, "user_id": user.user_id}
        )
        return user

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        await notify_admins(token, db, settings, request_id, f"Validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}", extra={"request_id": request_id})
        await notify_admins(token, db, settings, request_id, f"Authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )

async def notify_admins(token: str, db: AsyncSession, settings: Settings, request_id: Optional[str], error_message: str) -> None:
    """Notify admins of authentication failures."""
    query = select(Users).where(Users.has_role(Permission.MANAGE_USERS))
    result = await db.execute(query)
    admins = result.scalars().all()
    for admin in admins:
        await send_email(
            to_email=admin.email,
            subject="Authentication Failure Alert",
            body=(
                f"Dear {admin.first_name},\n\n"
                f"An authentication failure occurred at {func.current_timestamp()}.\n"
                f"Error: {error_message}\n"
                f"Token: {token[:10]}... (truncated for security)\n"
                f"Please review in the Employee Management System.\n\n"
                f"Best regards,\nEmployee Management System"
            ),
            request_id=request_id
        )

async def get_current_active_user(current_user: Users = Depends(get_current_user)) -> Users:
    """Ensure the current user is active."""
    request_id = get_request_id(current_user)
    if not current_user.is_active:
        logger.warning(
            f"Inactive user attempted access: {current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    return current_user

async def get_current_admin_user(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = Depends(get_request_id)
) -> Users:
    """Ensure the current user has admin permissions."""
    cache_key = f"user_permissions:{current_user.user_id}"
    cached_permissions = await get_cache(cache_key)
    if cached_permissions:
        user_permissions = [Permission[perm] for perm in cached_permissions]
    else:
        user_permissions = await get_user_permissions(current_user.user_id, db)
        await set_cache(cache_key, [perm.name for perm in user_permissions], ttl=300)
        logger.debug(f"Cache set for user_permissions:{current_user.user_id}")

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
        logger.warning(
            f"User {current_user.user_id} lacks admin permissions",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions for admin access")
    return current_user

async def get_current_super_admin_user(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = Depends(get_request_id)
) -> Users:
    """Ensure the current user has super admin permissions (ALL_PERMISSIONS)."""
    cache_key = f"user_permissions:{current_user.user_id}"
    cached_permissions = await get_cache(cache_key)
    if cached_permissions:
        user_permissions = [Permission[perm] for perm in cached_permissions]
    else:
        user_permissions = await get_user_permissions(current_user.user_id, db)
        await set_cache(cache_key, [perm.name for perm in user_permissions], ttl=300)
        logger.debug(f"Cache set for user_permissions:{current_user.user_id}")

    if Permission.ALL_PERMISSIONS not in user_permissions:
        logger.warning(
            f"User {current_user.user_id} lacks super admin permissions",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions for super admin access")
    return current_user

async def get_current_manager_user(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = Depends(get_request_id)
) -> Users:
    """Ensure the current user has manager permissions."""
    cache_key = f"user_permissions:{current_user.user_id}"
    cached_permissions = await get_cache(cache_key)
    if cached_permissions:
        user_permissions = [Permission[perm] for perm in cached_permissions]
    else:
        user_permissions = await get_user_permissions(current_user.user_id, db)
        await set_cache(cache_key, [perm.name for perm in user_permissions], ttl=300)
        logger.debug(f"Cache set for user_permissions:{current_user.user_id}")

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
        logger.warning(
            f"User {current_user.user_id} lacks manager permissions",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions for manager access")
    return current_user

async def get_current_hr_user(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = Depends(get_request_id)
) -> Users:
    """Ensure the current user has HR permissions."""
    cache_key = f"user_permissions:{current_user.user_id}"
    cached_permissions = await get_cache(cache_key)
    if cached_permissions:
        user_permissions = [Permission[perm] for perm in cached_permissions]
    else:
        user_permissions = await get_user_permissions(current_user.user_id, db)
        await set_cache(cache_key, [perm.name for perm in user_permissions], ttl=300)
        logger.debug(f"Cache set for user_permissions:{current_user.user_id}")

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
        logger.warning(
            f"User {current_user.user_id} lacks HR permissions",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions for HR access")
    return current_user

async def is_manager_or_hr(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = Depends(get_request_id)
) -> bool:
    """Check if the current user has manager or HR permissions."""
    cache_key = f"user_permissions:{current_user.user_id}"
    cached_permissions = await get_cache(cache_key)
    if cached_permissions:
        user_permissions = [Permission[perm] for perm in cached_permissions]
    else:
        user_permissions = await get_user_permissions(current_user.user_id, db)
        await set_cache(cache_key, [perm.name for perm in user_permissions], ttl=300)
        logger.debug(f"Cache set for user_permissions:{current_user.user_id}")

    management_perms = [
        Permission.APPROVE_LEAVE,
        Permission.MANAGE_EMPLOYEES,
        Permission.MANAGE_LEAVE_POLICIES,
        Permission.VIEW_TEAM_ATTENDANCE,
        Permission.ALL_PERMISSIONS
    ]

    has_management_permission = any(perm in user_permissions for perm in management_perms)
    if not has_management_permission:
        logger.warning(
            f"User {current_user.user_id} lacks manager or HR permissions",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
    return has_management_permission

async def validate_shift_or_leave(
    shift_assignment: Optional[ShiftAssignments] = None,
    leave_policy: Optional[LeavePolicies] = None,
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = Depends(get_request_id)
) -> None:
    """Validate shift assignment or leave policy and ensure user has management permissions."""
    if not shift_assignment and not leave_policy:
        logger.error("Neither shift_assignment nor leave_policy provided", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either shift_assignment or leave_policy must be provided"
        )

    if not await is_manager_or_hr(current_user, db, request_id):
        logger.warning(
            f"User {current_user.user_id} not authorized to manage shifts or leave policies",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to manage shifts or leave policies"
        )

    if shift_assignment:
        query = select(ShiftAssignments).where(
            ShiftAssignments.assignment_id == shift_assignment.assignment_id,
            ShiftAssignments.is_active == True,
            ShiftAssignments.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            logger.error(
                f"Shift assignment {shift_assignment.assignment_id} not found or inactive",
                extra={"request_id": request_id}
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shift assignment not found or inactive"
            )

    if leave_policy:
        query = select(LeavePolicies).where(
            LeavePolicies.policy_id == leave_policy.policy_id,
            LeavePolicies.is_active == True,
            LeavePolicies.deleted_at.is_(None),
            LeavePolicies.effective_from <= func.current_date(),
            or_(LeavePolicies.effective_to.is_(None), LeavePolicies.effective_to >= func.current_date())
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            logger.error(
                f"Leave policy {leave_policy.policy_id} not found or expired",
                extra={"request_id": request_id}
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Leave policy not found or expired"
            )