from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.leave_policies import LeavePolicies
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.schemas.leave_policy import LeavePolicyCreate, LeavePolicyUpdate, LeavePolicyOut
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission, EmployeeType
from app.core.exceptions import LeavePolicyNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

async def create_leave_policy(
    policy: LeavePolicyCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.CREATE_LEAVE_POLICY]))
) -> LeavePolicyOut:
    """Create a new leave policy with validation, version tracking, and logging."""
    try:
        query = select(LeavePolicies).where(
            LeavePolicies.leave_type == policy.leave_type,
            LeavePolicies.is_active.is_(True),
            LeavePolicies.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Leave policy type already exists"
            )

        db_policy = LeavePolicies(
            **policy.model_dump(),
            employee_type=policy.employee_type or EmployeeType.ALL,
            effective_from=datetime.now(timezone.utc).date(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            version=policy.version or 1
        )
        db.add(db_policy)
        await db.commit()
        await db.refresh(db_policy)

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_LEAVE_POLICY,
            table_affected="leave_policies",
            record_id=db_policy.policy_id,
            old_values=None,
            new_values=db_policy.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Leave policy created, policy_id: {db_policy.policy_id}, leave_type: {db_policy.leave_type}")
        return LeavePolicyOut.model_validate(db_policy)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating leave policy: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating leave policy"
        )

async def get_leave_policy(
    policy_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.VIEW_LEAVE_POLICY, Permission.VIEW_OWN_LEAVE_POLICY]))
) -> LeavePolicyOut:
    """Retrieve a leave policy by ID."""
    try:
        query = select(LeavePolicies).where(
            LeavePolicies.policy_id == policy_id,
            LeavePolicies.is_active.is_(True),
            LeavePolicies.deleted_at.is_(None)
        )
        result = await db.execute(query)
        policy = result.scalar_one_or_none()

        if not policy:
            raise LeavePolicyNotFoundError(leave_type=f"ID {policy_id}")

        if not any(p in current_user.permissions for p in [Permission.VIEW_LEAVE_POLICY, Permission.MANAGE_LEAVE]) and policy.employee_type != EmployeeType.ALL and policy.employee_type != current_user.employee_type:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this leave policy"
            )

        return LeavePolicyOut.model_validate(policy)

    except (LeavePolicyNotFoundError, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error retrieving leave policy {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving leave policy"
        )

async def list_leave_policies(
    skip: int = 0,
    limit: int = 50,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_LEAVE_POLICY, Permission.VIEW_OWN_LEAVE_POLICY]))
) -> List[LeavePolicyOut]:
    """Retrieve a list of active leave policies with pagination."""
    try:
        query = select(LeavePolicies).where(
            LeavePolicies.is_active.is_(True),
            LeavePolicies.deleted_at.is_(None)
        )
        if not any(p in current_user.permissions for p in [Permission.VIEW_LEAVE_POLICY, Permission.MANAGE_LEAVE]):
            query = query.where(
                (LeavePolicies.employee_type == EmployeeType.ALL) |
                (LeavePolicies.employee_type == current_user.employee_type)
            )

        query = query.offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        result = await db.execute(query)
        policies = result.scalars().all()

        logger.info(f"Retrieved {len(policies)} leave policies")
        return [LeavePolicyOut.model_validate(policy) for policy in policies]

    except Exception as e:
        logger.error(f"Error retrieving leave policies: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving leave policies"
        )

async def update_leave_policy(
    policy_id: int,
    policy_update: LeavePolicyUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.UPDATE_LEAVE_POLICY]))
) -> LeavePolicyOut:
    """Update a leave policy with validation, version increment, and logging."""
    try:
        query = select(LeavePolicies).where(
            LeavePolicies.policy_id == policy_id,
            LeavePolicies.is_active.is_(True),
            LeavePolicies.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_policy = result.scalar_one_or_none()

        if not db_policy:
            raise LeavePolicyNotFoundError(leave_type=f"ID {policy_id}")

        update_data = policy_update.model_dump(exclude_none=True)
        if "leave_type" in update_data:
            query = select(LeavePolicies).where(
                LeavePolicies.leave_type == update_data["leave_type"],
                LeavePolicies.policy_id != policy_id,
                LeavePolicies.is_active.is_(True),
                LeavePolicies.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Leave policy type already exists"
                )

        old_values = db_policy.__dict__.copy()
        for key, value in update_data.items():
            setattr(db_policy, key, value)
        db_policy.version += 1
        db_policy.updated_at = datetime.now(timezone.utc)
        db.add(db_policy)
        await db.commit()
        await db.refresh(db_policy)

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_LEAVE_POLICY,
            table_affected="leave_policies",
            record_id=policy_id,
            old_values=old_values,
            new_values=db_policy.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Leave policy updated, policy_id: {policy_id}, version: {db_policy.version}")
        return LeavePolicyOut.model_validate(db_policy)

    except (LeavePolicyNotFoundError, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error updating leave policy {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating leave policy"
        )

async def delete_leave_policy(
    policy_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.DELETE_LEAVE_POLICY]))
) -> None:
    """Soft delete a leave policy with logging."""
    try:
        query = select(LeavePolicies).where(
            LeavePolicies.policy_id == policy_id,
            LeavePolicies.is_active.is_(True),
            LeavePolicies.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_policy = result.scalar_one_or_none()

        if not db_policy:
            raise LeavePolicyNotFoundError(leave_type=f"ID {policy_id}")

        db_policy.is_active = False
        db_policy.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_LEAVE_POLICY,
            table_affected="leave_policies",
            record_id=policy_id,
            old_values=db_policy.__dict__,
            new_values=None,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Leave policy soft deleted, policy_id: {policy_id}")

    except LeavePolicyNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error deleting leave policy {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting leave policy"
        )