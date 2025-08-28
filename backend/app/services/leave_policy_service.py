from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from datetime import datetime, timezone, date
from app.models.leave_policies import LeavePolicies
from app.models.users import Users
from app.models.leave_balances import LeaveBalances
from app.schemas.leave_policy import LeavePolicyCreate, LeavePolicyUpdate, LeavePolicyOut
from app.schemas.system_log import SystemLogCreate
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission, EmployeeType
from app.core.mail import send_email
from app.core.exceptions import LeavePolicyNotFoundError, ValidationError
from app.core.security import get_current_user
from app.core.permissions import require_permissions_dependency, invalidate_user_cache, get_user_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_leave_policy_exists
from app.core.utils import get_request_id, get_users_with_permission
from app.services.system_log_service import create_system_log
import logging

logger = logging.getLogger(__name__)

async def create_leave_policy(
    policy: LeavePolicyCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.CREATE_LEAVE_POLICY]))
) -> LeavePolicyOut:
    """Create a new leave policy with validation, version tracking, and logging."""
    try:
        # Validate inputs
        if policy.effective_from < date.today():
            raise ValidationError(detail="Effective date cannot be in the past")
        if policy.annual_allocation < 0 or policy.carry_forward_limit < 0:
            raise ValidationError(detail="Annual allocation and carry forward limit must be non-negative")
        if policy.employee_type not in EmployeeType:
            raise ValidationError(detail=f"Invalid employee type: {policy.employee_type}")

        # Validate unique constraint
        query = select(LeavePolicies).where(
            LeavePolicies.employee_type == policy.employee_type,
            LeavePolicies.leave_type == policy.leave_type,
            LeavePolicies.effective_from == policy.effective_from,
            LeavePolicies.is_active.is_(True),
            LeavePolicies.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ValidationError(detail=f"Leave policy for {policy.employee_type} and {policy.leave_type} on {policy.effective_from} already exists")

        # Create policy
        db_policy = LeavePolicies(
            **policy.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            version=policy.version or 1,
            is_active=True
        )
        db.add(db_policy)
        await db.commit()
        await db.refresh(db_policy)

        # Update leave balances
        query_users = select(Users).where(
            and_(
                Users.is_active.is_(True),
                Users.deleted_at.is_(None),
                or_(Users.employee_type == policy.employee_type, policy.employee_type == EmployeeType.ALL)
            )
        )
        result_users = await db.execute(query_users)
        users = result_users.scalars().all()
        for user in users:
            query_balance = select(LeaveBalances).where(
                LeaveBalances.user_id == user.user_id,
                LeaveBalances.leave_type == policy.leave_type,
                LeaveBalances.is_active.is_(True),
                LeaveBalances.deleted_at.is_(None)
            )
            result_balance = await db.execute(query_balance)
            leave_balance = result_balance.scalar_one_or_none()
            if leave_balance:
                leave_balance.allocated_days = policy.annual_allocation
                leave_balance.carried_forward = min(leave_balance.carried_forward, policy.carry_forward_limit)
                leave_balance.updated_at = datetime.now(timezone.utc)
            else:
                leave_balance = LeaveBalances(
                    user_id=user.user_id,
                    leave_type=policy.leave_type,
                    allocated_days=policy.annual_allocation,
                    used_days=0,
                    carried_forward=0,
                    is_active=True,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
            db.add(leave_balance)
            invalidate_user_cache(user.user_id)
        await db.commit()

        # Invalidate caches
        await invalidate_cache_prefix("leave_policies")
        await invalidate_cache_prefix("leave_balances")
        invalidate_user_cache(current_user.user_id)  # Invalidate current user's cache for permission updates
        logger.info(
            f"Cache invalidated for leave_policies, leave_balances, {len(users)} users, and current_user:{current_user.user_id}",
            extra={"request_id": request_id}
        )

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_LEAVE_POLICY,
            table_affected="leave_policies",
            record_id=db_policy.policy_id,
            old_values=None,
            new_values=db_policy.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        # Notify admins
        admins = await get_users_with_permission(Permission.MANAGE_LEAVE, db)
        for admin in admins:
            await send_email(
                to_email=admin.email,
                subject=f"New Leave Policy Created (ID: {db_policy.policy_id})",
                body=(
                    f"Dear {admin.first_name},\n\n"
                    f"A new leave policy for {db_policy.employee_type} and {db_policy.leave_type} has been created.\n"
                    f"Details: {db_policy.annual_allocation} days, effective from {db_policy.effective_from}.\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        logger.info(
            f"Leave policy created, policy_id: {db_policy.policy_id}, leave_type: {db_policy.leave_type}, employee_type: {db_policy.employee_type}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return LeavePolicyOut.model_validate(db_policy)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating leave policy: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating leave policy")

async def get_leave_policy(
    policy_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_LEAVE_POLICY, Permission.VIEW_OWN_LEAVE_POLICY]))
) -> LeavePolicyOut:
    """Retrieve a leave policy by ID with caching."""
    try:
        if policy_id <= 0:
            raise ValidationError(detail="Invalid policy_id")

        cache_key = f"leave_policy:{policy_id}"
        cached_policy = await get_cache(cache_key)
        if cached_policy:
            logger.info(f"Cache hit for policy_id: {policy_id}", extra={"request_id": request_id})
            return LeavePolicyOut(**cached_policy)

        await validate_leave_policy_exists(db, policy_id, request_id)

        query = select(LeavePolicies).where(
            LeavePolicies.policy_id == policy_id,
            LeavePolicies.is_active.is_(True),
            LeavePolicies.deleted_at.is_(None)
        )
        result = await db.execute(query)
        policy = result.scalar_one_or_none()
        if not policy:
            raise LeavePolicyNotFoundError(leave_type=f"ID {policy_id}")

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if Permission.VIEW_LEAVE_POLICY not in user_permissions and Permission.MANAGE_LEAVE not in user_permissions:
            if policy.employee_type != EmployeeType.ALL and policy.employee_type != current_user.employee_type:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view this leave policy"
                )

        policy_dict = LeavePolicyOut.model_validate(policy).model_dump()
        await set_cache(cache_key, policy_dict, ttl=300)
        logger.info(f"Cache set for policy_id: {policy_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved leave policy, policy_id: {policy_id}, leave_type: {policy.leave_type}, employee_type: {policy.employee_type}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return LeavePolicyOut.model_validate(policy)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except LeavePolicyNotFoundError as e:
        logger.error(f"Leave policy not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Forbidden access to leave policy {policy_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave policy {policy_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave policy")

async def list_leave_policies(
    employee_type: Optional[EmployeeType] = None,
    leave_type: Optional[str] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_LEAVE_POLICY, Permission.VIEW_OWN_LEAVE_POLICY]))
) -> List[LeavePolicyOut]:
    """Retrieve a list of active leave policies with pagination and filtering."""
    try:
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")
        if employee_type and employee_type not in EmployeeType:
            raise ValidationError(detail=f"Invalid employee type: {employee_type}")

        cache_key = f"leave_policies:{employee_type or 'all'}:{leave_type or 'all'}:{skip}:{limit or settings.DEFAULT_PAGE_SIZE}"
        cached_policies = await get_cache(cache_key)
        if cached_policies:
            logger.info(f"Cache hit for leave_policies, employee_type: {employee_type or 'all'}, leave_type: {leave_type or 'all'}", extra={"request_id": request_id})
            return [LeavePolicyOut(**policy) for policy in cached_policies]

        query = select(LeavePolicies).where(
            LeavePolicies.is_active.is_(True),
            LeavePolicies.deleted_at.is_(None)
        )
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if Permission.VIEW_LEAVE_POLICY not in user_permissions and Permission.MANAGE_LEAVE not in user_permissions:
            query = query.where(
                (LeavePolicies.employee_type == EmployeeType.ALL) |
                (LeavePolicies.employee_type == current_user.employee_type)
            )
        if employee_type:
            query = query.where(LeavePolicies.employee_type == employee_type)
        if leave_type:
            query = query.where(LeavePolicies.leave_type == leave_type)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = query.order_by(LeavePolicies.effective_from.asc()).offset(skip).limit(limit)
        result = await db.execute(query)
        policies = result.scalars().all()

        policies_dict = [LeavePolicyOut.model_validate(policy).model_dump() for policy in policies]
        await set_cache(cache_key, policies_dict, ttl=300)
        logger.info(f"Cache set for leave_policies, employee_type: {employee_type or 'all'}, leave_type: {leave_type or 'all'}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(policies)} leave policies, employee_type: {employee_type or 'all'}, leave_type: {leave_type or 'all'}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [LeavePolicyOut.model_validate(policy) for policy in policies]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave policies: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave policies")

async def update_leave_policy(
    policy_id: int,
    policy_update: LeavePolicyUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.UPDATE_LEAVE_POLICY]))
) -> LeavePolicyOut:
    """Update a leave policy with validation, version increment, and logging."""
    try:
        if policy_id <= 0:
            raise ValidationError(detail="Invalid policy_id")
        if policy_update.annual_allocation is not None and policy_update.annual_allocation < 0:
            raise ValidationError(detail="Annual allocation must be non-negative")
        if policy_update.carry_forward_limit is not None and policy_update.carry_forward_limit < 0:
            raise ValidationError(detail="Carry forward limit must be non-negative")
        if policy_update.employee_type and policy_update.employee_type not in EmployeeType:
            raise ValidationError(detail=f"Invalid employee type: {policy_update.employee_type}")

        await validate_leave_policy_exists(db, policy_id, request_id)

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
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        # Validate version for optimistic locking
        if "version" in update_data and update_data["version"] != db_policy.version:
            raise ValidationError(detail="Version mismatch, policy has been updated by another user")

        # Validate unique constraint
        if any(k in update_data for k in ["employee_type", "leave_type", "effective_from"]):
            employee_type = update_data.get("employee_type", db_policy.employee_type)
            leave_type = update_data.get("leave_type", db_policy.leave_type)
            effective_from = update_data.get("effective_from", db_policy.effective_from)
            query = select(LeavePolicies).where(
                LeavePolicies.employee_type == employee_type,
                LeavePolicies.leave_type == leave_type,
                LeavePolicies.effective_from == effective_from,
                LeavePolicies.policy_id != policy_id,
                LeavePolicies.is_active.is_(True),
                LeavePolicies.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise ValidationError(detail=f"Leave policy for {employee_type} and {leave_type} on {effective_from} already exists")

        old_values = db_policy.__dict__.copy()
        for key, value in update_data.items():
            setattr(db_policy, key, value)
        db_policy.version += 1
        db_policy.updated_at = datetime.now(timezone.utc)
        db.add(db_policy)
        await db.commit()
        await db.refresh(db_policy)

        # Update leave balances
        query_users = select(Users).where(
            and_(
                Users.is_active.is_(True),
                Users.deleted_at.is_(None),
                or_(Users.employee_type == db_policy.employee_type, db_policy.employee_type == EmployeeType.ALL)
            )
        )
        result_users = await db.execute(query_users)
        users = result_users.scalars().all()
        for user in users:
            query_balance = select(LeaveBalances).where(
                LeaveBalances.user_id == user.user_id,
                LeaveBalances.leave_type == db_policy.leave_type,
                LeaveBalances.is_active.is_(True),
                LeaveBalances.deleted_at.is_(None)
            )
            result_balance = await db.execute(query_balance)
            leave_balance = result_balance.scalar_one_or_none()
            if leave_balance:
                if "annual_allocation" in update_data:
                    leave_balance.allocated_days = db_policy.annual_allocation
                if "carry_forward_limit" in update_data:
                    leave_balance.carried_forward = min(leave_balance.carried_forward, db_policy.carry_forward_limit)
                leave_balance.updated_at = datetime.now(timezone.utc)
                db.add(leave_balance)
                invalidate_user_cache(user.user_id)
        await db.commit()

        # Invalidate caches
        await invalidate_cache_prefix("leave_policies")
        await invalidate_cache_prefix("leave_balances")
        invalidate_user_cache(current_user.user_id)  # Invalidate current user's cache for permission updates
        logger.info(
            f"Cache invalidated for leave_policies, leave_balances, {len(users)} users, and current_user:{current_user.user_id}",
            extra={"request_id": request_id}
        )

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_LEAVE_POLICY,
            table_affected="leave_policies",
            record_id=policy_id,
            old_values=old_values,
            new_values=db_policy.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        # Notify admins
        admins = await get_users_with_permission(Permission.MANAGE_LEAVE, db)
        for admin in admins:
            await send_email(
                to_email=admin.email,
                subject=f"Leave Policy Updated (ID: {db_policy.policy_id})",
                body=(
                    f"Dear {admin.first_name},\n\n"
                    f"The leave policy (ID: {db_policy.policy_id}) for {db_policy.employee_type} and {db_policy.leave_type} "
                    f"has been updated to version {db_policy.version}.\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        logger.info(
            f"Leave policy updated, policy_id: {policy_id}, leave_type: {db_policy.leave_type}, version: {db_policy.version}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return LeavePolicyOut.model_validate(db_policy)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except LeavePolicyNotFoundError as e:
        logger.error(f"Leave policy not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error updating leave policy {policy_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating leave policy")

async def delete_leave_policy(
    policy_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.DELETE_LEAVE_POLICY]))
) -> None:
    """Soft delete a leave policy with validation, logging, and notification."""
    try:
        if policy_id <= 0:
            raise ValidationError(detail="Invalid policy_id")

        await validate_leave_policy_exists(db, policy_id, request_id)

        query = select(LeavePolicies).where(
            LeavePolicies.policy_id == policy_id,
            LeavePolicies.is_active.is_(True),
            LeavePolicies.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_policy = result.scalar_one_or_none()
        if not db_policy:
            raise LeavePolicyNotFoundError(leave_type=f"ID {policy_id}")

        # Check if this is the only active policy for the leave_type and employee_type
        query_check = select(LeavePolicies).where(
            LeavePolicies.leave_type == db_policy.leave_type,
            LeavePolicies.employee_type == db_policy.employee_type,
            LeavePolicies.policy_id != policy_id,
            LeavePolicies.is_active.is_(True),
            LeavePolicies.deleted_at.is_(None)
        )
        result_check = await db.execute(query_check)
        if not result_check.scalars().all():
            raise ValidationError(detail=f"Cannot delete the only active policy for {db_policy.employee_type} and {db_policy.leave_type}")

        db_policy.is_active = False
        db_policy.deleted_at = datetime.now(timezone.utc)
        db_policy.updated_at = datetime.now(timezone.utc)
        db.add(db_policy)
        await db.commit()

        # Invalidate caches for affected users
        query_users = select(Users).where(
            and_(
                Users.is_active.is_(True),
                Users.deleted_at.is_(None),
                or_(Users.employee_type == db_policy.employee_type, db_policy.employee_type == EmployeeType.ALL)
            )
        )
        result_users = await db.execute(query_users)
        users = result_users.scalars().all()
        for user in users:
            invalidate_user_cache(user.user_id)

        # Invalidate caches
        await invalidate_cache_prefix("leave_policies")
        await invalidate_cache_prefix("leave_balances")
        invalidate_user_cache(current_user.user_id)  # Invalidate current user's cache for permission updates
        logger.info(
            f"Cache invalidated for leave_policies, leave_balances, {len(users)} users, and current_user:{current_user.user_id}",
            extra={"request_id": request_id}
        )

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_LEAVE_POLICY,
            table_affected="leave_policies",
            record_id=policy_id,
            old_values=db_policy.__dict__,
            new_values=None,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        # Notify admins
        admins = await get_users_with_permission(Permission.MANAGE_LEAVE, db)
        for admin in admins:
            await send_email(
                to_email=admin.email,
                subject=f"Leave Policy Deleted (ID: {policy_id})",
                body=(
                    f"Dear {admin.first_name},\n\n"
                    f"The leave policy (ID: {policy_id}) for {db_policy.employee_type} and {db_policy.leave_type} "
                    f"has been deleted.\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        logger.info(
            f"Leave policy soft deleted, policy_id: {policy_id}, leave_type: {db_policy.leave_type}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except LeavePolicyNotFoundError as e:
        logger.error(f"Leave policy not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error deleting leave policy {policy_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting leave policy")