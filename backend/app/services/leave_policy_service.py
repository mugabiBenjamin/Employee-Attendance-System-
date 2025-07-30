from typing import List, Optional
from fastapi import HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.leave_policies import LeavePolicies
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.schemas.leave_policy import LeavePolicyCreate, LeavePolicyUpdate, LeavePolicyOut
from app.core.config import settings
from app.core.enums import SystemAction
from app.core.exceptions import LeavePolicyNotFoundError
from app.core.security import get_current_user
from app.core.permissions import check_permission
import logging

logger = logging.getLogger(__name__)

async def create_leave_policy(
    db: AsyncSession,
    policy: LeavePolicyCreate,
    current_user: Users = Depends(get_current_user),
    _: str = Depends(check_permission("create_leave_policy"))
) -> LeavePolicyOut:
    """
    Create a new leave policy with validation, version tracking, and logging.
    """
    try:
        # Check for existing leave policy with same type
        query = select(LeavePolicies).where(
            LeavePolicies.leave_type == policy.leave_type,
            LeavePolicies.is_active == True,
            LeavePolicies.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Leave policy type already exists"
            )

        # Create leave policy
        db_policy = LeavePolicies(
            employee_type=policy.employee_type or "all",
            leave_type=policy.leave_type,
            annual_allocation=policy.max_days,
            carry_forward_limit=policy.carryover_limit or 0,
            max_consecutive_days=policy.max_days,
            requires_approval=True,
            approval_levels=1,
            accrual_rate=policy.accrual_rate or 0,
            effective_from=datetime.now(timezone.utc).date(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            version=policy.version
        )
        db.add(db_policy)
        await db.commit()
        await db.refresh(db_policy)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="leave_policies",
            record_id=db_policy.policy_id,
            old_values=None,
            new_values=db_policy.__dict__,
            ip_address=None,
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

async def get_leave_policy_by_id(
    db: AsyncSession,
    policy_id: int,
    _: str = Depends(check_permission("view_leave_policy"))
) -> Optional[LeavePolicyOut]:
    """
    Retrieve a leave policy by ID.
    """
    try:
        query = select(LeavePolicies).where(
            LeavePolicies.policy_id == policy_id,
            LeavePolicies.is_active == True,
            LeavePolicies.deleted_at == None
        )
        result = await db.execute(query)
        policy = result.scalar_one_or_none()

        if not policy:
            raise LeavePolicyNotFoundError()

        return LeavePolicyOut.model_validate(policy)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving leave policy {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving leave policy"
        )

async def get_leave_policies(
    db: AsyncSession,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    _: str = Depends(check_permission("view_leave_policy"))
) -> List[LeavePolicyOut]:
    """
    Retrieve a list of active leave policies with pagination.
    """
    try:
        query = select(LeavePolicies).where(
            LeavePolicies.is_active == True,
            LeavePolicies.deleted_at == None
        ).offset(skip).limit(limit)
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
    db: AsyncSession,
    policy_id: int,
    policy_update: LeavePolicyUpdate,
    current_user: Users = Depends(get_current_user),
    _: str = Depends(check_permission("update_leave_policy"))
) -> LeavePolicyOut:
    """
    Update a leave policy with validation, version increment, and logging.
    """
    try:
        # Retrieve policy
        query = select(LeavePolicies).where(
            LeavePolicies.policy_id == policy_id,
            LeavePolicies.is_active == True,
            LeavePolicies.deleted_at == None
        )
        result = await db.execute(query)
        db_policy = result.scalar_one_or_none()

        if not db_policy:
            raise LeavePolicyNotFoundError()

        # Check for duplicate leave type if updated
        update_data = policy_update.model_dump(exclude_none=True)
        if "leave_type" in update_data:
            query = select(LeavePolicies).where(
                LeavePolicies.leave_type == update_data["leave_type"],
                LeavePolicies.policy_id != policy_id,
                LeavePolicies.is_active == True,
                LeavePolicies.deleted_at == None
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Leave policy type already exists"
                )

        # Store old values for logging
        old_values = db_policy.__dict__.copy()

        # Apply updates
        for key, value in update_data.items():
            setattr(db_policy, key, value)
        db_policy.version += 1
        db_policy.updated_at = datetime.now(timezone.utc)
        db.add(db_policy)
        await db.commit()
        await db.refresh(db_policy)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE,
            table_affected="leave_policies",
            record_id=policy_id,
            old_values=old_values,
            new_values=db_policy.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Leave policy updated, policy_id: {policy_id}, version: {db_policy.version}")
        return LeavePolicyOut.model_validate(db_policy)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating leave policy {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating leave policy"
        )

async def delete_leave_policy(
    db: AsyncSession,
    policy_id: int,
    current_user: Users = Depends(get_current_user),
    _: str = Depends(check_permission("delete_leave_policy"))
) -> None:
    """
    Soft delete a leave policy with logging.
    """
    try:
        query = select(LeavePolicies).where(
            LeavePolicies.policy_id == policy_id,
            LeavePolicies.is_active == True,
            LeavePolicies.deleted_at == None
        )
        result = await db.execute(query)
        db_policy = result.scalar_one_or_none()

        if not db_policy:
            raise LeavePolicyNotFoundError()

        db_policy.is_active = False
        db_policy.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.DELETE,
            table_affected="leave_policies",
            record_id=policy_id,
            old_values=db_policy.__dict__,
            new_values=None,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Leave policy soft deleted, policy_id: {policy_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting leave policy {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting leave policy"
        )