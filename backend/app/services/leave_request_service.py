from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from datetime import date, datetime, timezone
from app.models.leave_requests import LeaveRequests
from app.models.users import Users
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.leave_balances import LeaveBalances
from app.schemas.leave_request import LeaveRequestCreate, LeaveRequestUpdate, LeaveRequestOut, LeaveApprovalUpdate
from app.schemas.system_log import SystemLogCreate
from app.core.config import Settings, get_settings
from app.core.enums import LeaveRequestStatus, SystemAction, Permission
from app.core.mail import send_email
from app.core.exceptions import LeaveRequestNotFoundError, LeaveBalanceNotFoundError, ValidationError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_leave_request_exists
from app.services.system_log_service import create_system_log
import logging

logger = logging.getLogger(__name__)

async def validate_no_overlapping_leave_requests(
    db: AsyncSession,
    user_id: int,
    start_date: date,
    end_date: date,
    leave_id: Optional[int] = None,
    request_id: Optional[str] = None
) -> None:
    query = select(LeaveRequests).where(
        LeaveRequests.user_id == user_id,
        LeaveRequests.status != LeaveRequestStatus.REJECTED,
        LeaveRequests.is_active.is_(True),
        LeaveRequests.deleted_at.is_(None),
        or_(
            and_(
                LeaveRequests.start_date <= end_date,
                LeaveRequests.end_date >= start_date
            )
        )
    )
    if leave_id:
        query = query.where(LeaveRequests.leave_id != leave_id)
    result = await db.execute(query)
    if result.scalars().first():
        raise ValidationError(detail="Overlapping leave request exists")

async def create_leave_request(
    leave_request: LeaveRequestCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.CREATE_LEAVE_REQUEST]))
) -> LeaveRequestOut:
    """Create a new leave request with validation, logging, and notification."""
    try:
        if leave_request.user_id <= 0:
            raise ValidationError(detail="Invalid user_id")

        # Validate overlapping leave requests
        await validate_no_overlapping_leave_requests(
            db, current_user.user_id, leave_request.start_date, leave_request.end_date, request_id=request_id
        )

        # Validate leave balance
        query = select(LeaveBalances).where(
            LeaveBalances.user_id == current_user.user_id,
            LeaveBalances.leave_type == leave_request.leave_type,
            LeaveBalances.is_active.is_(True),
            LeaveBalances.deleted_at.is_(None)
        )
        result = await db.execute(query)
        leave_balance = result.scalar_one_or_none()
        if not leave_balance:
            raise LeaveBalanceNotFoundError(user_id=current_user.user_id, leave_type=leave_request.leave_type)

        days_requested = (leave_request.end_date - leave_request.start_date).days + 1
        available_days = leave_balance.allocated_days - leave_balance.used_days + leave_balance.carried_forward
        if days_requested > available_days:
            raise ValidationError(detail="Insufficient leave balance")

        # Create leave request
        db_leave_request = LeaveRequests(
            user_id=current_user.user_id,
            leave_type=leave_request.leave_type,
            start_date=leave_request.start_date,
            end_date=leave_request.end_date,
            days_requested=days_requested,
            reason=leave_request.reason,
            status=LeaveRequestStatus.UNDER_REVIEW,
            attachment_url=str(leave_request.attachment_url) if leave_request.attachment_url else None,
            is_active=leave_request.is_active,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_leave_request)
        await db.commit()
        await db.refresh(db_leave_request)

        # Invalidate cache
        await invalidate_cache_prefix("leave_requests")
        logger.debug(f"Cache cleared for leave_requests")

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_LEAVE_REQUEST,
            table_affected="leave_requests",
            record_id=db_leave_request.leave_id,
            old_values=None,
            new_values=db_leave_request.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        # Notify manager and admins
        query = select(Users).join(
            EmployeeHierarchy,
            EmployeeHierarchy.manager_id == Users.user_id
        ).where(
            EmployeeHierarchy.employee_id == current_user.user_id,
            EmployeeHierarchy.is_active.is_(True),
            EmployeeHierarchy.deleted_at.is_(None)
        )
        result = await db.execute(query)
        manager = result.scalar_one_or_none()
        query_admins = select(Users).where(Users.has_role(Permission.MANAGE_LEAVE))
        result_admins = await db.execute(query_admins)
        admins = result_admins.scalars().all()
        recipients = [(manager.email, manager.first_name)] if manager else []
        recipients += [(admin.email, admin.first_name) for admin in admins]
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"New Leave Request Submitted (ID: {db_leave_request.leave_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"Employee {current_user.first_name} {current_user.last_name} submitted a leave request.\n"
                    f"Details:\n"
                    f"Leave Type: {leave_request.leave_type.value.capitalize()}\n"
                    f"Start Date: {leave_request.start_date}\n"
                    f"End Date: {leave_request.end_date}\n"
                    f"Reason: {leave_request.reason or 'None'}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        logger.info(
            f"Leave request created, leave_id: {db_leave_request.leave_id}, user_id: {current_user.user_id}",
            extra={"request_id": request_id}
        )
        return LeaveRequestOut.model_validate(db_leave_request)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except LeaveBalanceNotFoundError as e:
        logger.error(f"Leave balance not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating leave request for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating leave request")

async def get_leave_request(
    leave_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_LEAVE_REQUEST, Permission.VIEW_OWN_LEAVE_REQUEST]))
) -> LeaveRequestOut:
    """Retrieve a leave request by ID for the current user or their subordinates with caching."""
    try:
        if leave_id <= 0:
            raise ValidationError(detail="Invalid leave_id")

        cache_key = f"leave_request:{leave_id}"
        cached_request = await get_cache(cache_key)
        if cached_request:
            return LeaveRequestOut(**cached_request)

        await validate_leave_request_exists(db, leave_id, request_id)

        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == leave_id,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        if not any(p in current_user.permissions for p in [Permission.VIEW_LEAVE_REQUEST, Permission.MANAGE_LEAVE]):
            query = query.join(
                EmployeeHierarchy,
                EmployeeHierarchy.employee_id == LeaveRequests.user_id,
                isouter=True
            ).where(
                or_(
                    LeaveRequests.user_id == current_user.user_id,
                    EmployeeHierarchy.manager_id == current_user.user_id,
                    EmployeeHierarchy.is_active.is_(True),
                    EmployeeHierarchy.deleted_at.is_(None)
                )
            )
        result = await db.execute(query)
        leave_request = result.scalar_one_or_none()

        if not leave_request:
            raise LeaveRequestNotFoundError(leave_id=leave_id)

        leave_request_dict = LeaveRequestOut.model_validate(leave_request).model_dump()
        await set_cache(cache_key, leave_request_dict, ttl=300)

        logger.info(
            f"Retrieved leave request, leave_id: {leave_id}, user_id: {current_user.user_id}",
            extra={"request_id": request_id}
        )
        return LeaveRequestOut.model_validate(leave_request)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except LeaveRequestNotFoundError as e:
        logger.error(f"Leave request not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave request {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave request")

async def get_leave_requests(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_LEAVE_REQUEST, Permission.VIEW_OWN_LEAVE_REQUEST]))
) -> List[LeaveRequestOut]:
    """Retrieve a list of leave requests for the current user or their subordinates with pagination and caching."""
    try:
        limit = limit or settings.DEFAULT_PAGE_SIZE
        if skip < 0 or limit <= 0:
            raise ValidationError(detail="Invalid pagination parameters")
        if user_id is not None and user_id <= 0:
            raise ValidationError(detail="Invalid user_id")

        cache_key = f"leave_requests:{user_id or 'all'}:{skip}:{limit}"
        cached_requests = await get_cache(cache_key)
        if cached_requests:
            return [LeaveRequestOut(**req) for req in cached_requests]

        query = select(LeaveRequests).where(
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        if user_id:
            query = query.where(LeaveRequests.user_id == user_id)
        if not any(p in current_user.permissions for p in [Permission.VIEW_LEAVE_REQUEST, Permission.MANAGE_LEAVE]):
            query = query.join(
                EmployeeHierarchy,
                EmployeeHierarchy.employee_id == LeaveRequests.user_id,
                isouter=True
            ).where(
                or_(
                    LeaveRequests.user_id == current_user.user_id,
                    EmployeeHierarchy.manager_id == current_user.user_id,
                    EmployeeHierarchy.is_active.is_(True),
                    EmployeeHierarchy.deleted_at.is_(None)
                )
            )
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        leave_requests = result.scalars().all()

        leave_requests_dict = [LeaveRequestOut.model_validate(req).model_dump() for req in leave_requests]
        await set_cache(cache_key, leave_requests_dict, ttl=300)

        logger.info(
            f"Retrieved {len(leave_requests)} leave requests for user_id: {current_user.user_id}",
            extra={"request_id": request_id}
        )
        return [LeaveRequestOut.model_validate(req) for req in leave_requests]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave requests for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave requests")

async def update_leave_request(
    leave_id: int,
    leave_request_update: LeaveRequestUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.UPDATE_LEAVE_REQUEST]))
) -> LeaveRequestOut:
    """Update a leave request with validation, logging, and notification."""
    try:
        if leave_id <= 0:
            raise ValidationError(detail="Invalid leave_id")

        await validate_leave_request_exists(db, leave_id, request_id)

        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == leave_id,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_leave_request = result.scalar_one_or_none()
        if not db_leave_request:
            raise LeaveRequestNotFoundError(leave_id=leave_id)

        update_data = leave_request_update.model_dump(exclude_none=True)
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        # Validate user_id if updated
        if "user_id" in update_data and update_data["user_id"] != db_leave_request.user_id:
            query = select(Users).where(
                Users.user_id == update_data["user_id"],
                Users.is_active.is_(True),
                Users.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise ValidationError(detail=f"User {update_data['user_id']} not found")

        # Validate leave balance if leave_type, start_date, or end_date are updated
        if any(k in update_data for k in ["leave_type", "start_date", "end_date"]):
            leave_type = update_data.get("leave_type", db_leave_request.leave_type)
            start_date = update_data.get("start_date", db_leave_request.start_date)
            end_date = update_data.get("end_date", db_leave_request.end_date)
            days_requested = (end_date - start_date).days + 1
            query = select(LeaveBalances).where(
                LeaveBalances.user_id == db_leave_request.user_id,
                LeaveBalances.leave_type == leave_type,
                LeaveBalances.is_active.is_(True),
                LeaveBalances.deleted_at.is_(None)
            )
            result = await db.execute(query)
            leave_balance = result.scalar_one_or_none()
            if not leave_balance:
                raise LeaveBalanceNotFoundError(user_id=db_leave_request.user_id, leave_type=leave_type)
            available_days = leave_balance.allocated_days - leave_balance.used_days + leave_balance.carried_forward
            if days_requested > available_days:
                raise ValidationError(detail="Insufficient leave balance")
            update_data["days_requested"] = days_requested

        # Validate overlapping leave requests if dates are updated
        if "start_date" in update_data or "end_date" in update_data:
            start_date = update_data.get("start_date", db_leave_request.start_date)
            end_date = update_data.get("end_date", db_leave_request.end_date)
            await validate_no_overlapping_leave_requests(
                db, db_leave_request.user_id, start_date, end_date, leave_id, request_id
            )

        old_values = db_leave_request.__dict__.copy()
        for key, value in update_data.items():
            setattr(db_leave_request, key, value)
        db_leave_request.updated_at = datetime.now(timezone.utc)
        db.add(db_leave_request)
        await db.commit()
        await db.refresh(db_leave_request)

        # Invalidate cache
        await invalidate_cache_prefix("leave_requests")
        logger.debug(f"Cache cleared for leave_requests")

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_LEAVE_REQUEST,
            table_affected="leave_requests",
            record_id=leave_id,
            old_values=old_values,
            new_values=db_leave_request.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        # Notify employee and admins
        query_user = select(Users).where(Users.user_id == db_leave_request.user_id)
        result_user = await db.execute(query_user)
        employee = result_user.scalar_one_or_none()
        query_admins = select(Users).where(Users.has_role(Permission.MANAGE_LEAVE))
        result_admins = await db.execute(query_admins)
        admins = result_admins.scalars().all()
        recipients = [(employee.email, employee.first_name)] + [(admin.email, admin.first_name) for admin in admins]
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"Leave Request Updated (ID: {db_leave_request.leave_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"The leave request (ID: {db_leave_request.leave_id}) has been updated.\n"
                    f"Details:\n"
                    f"Leave Type: {db_leave_request.leave_type.value.capitalize()}\n"
                    f"Start Date: {db_leave_request.start_date}\n"
                    f"End Date: {db_leave_request.end_date}\n"
                    f"Reason: {db_leave_request.reason or 'None'}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        logger.info(
            f"Leave request updated, leave_id: {leave_id}, user_id: {current_user.user_id}",
            extra={"request_id": request_id}
        )
        return LeaveRequestOut.model_validate(db_leave_request)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except LeaveRequestNotFoundError as e:
        logger.error(f"Leave request not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except LeaveBalanceNotFoundError as e:
        logger.error(f"Leave balance not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error updating leave request {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating leave request")

async def approve_reject_leave_request(
    leave_id: int,
    approval: LeaveApprovalUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.APPROVE_LEAVE]))
) -> LeaveRequestOut:
    """Approve or reject a leave request, update balance, and notify user."""
    try:
        if leave_id <= 0:
            raise ValidationError(detail="Invalid leave_id")

        await validate_leave_request_exists(db, leave_id, request_id)

        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == leave_id,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result = await db.execute(query)
        leave_request = result.scalar_one_or_none()
        if not leave_request:
            raise LeaveRequestNotFoundError(leave_id=leave_id)

        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.employee_id == leave_request.user_id,
            EmployeeHierarchy.manager_id == current_user.user_id,
            EmployeeHierarchy.is_active.is_(True),
            EmployeeHierarchy.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none() and not current_user.has_role(Permission.MANAGE_LEAVE):
            raise ValidationError(detail="Not authorized to approve this leave request")

        old_values = leave_request.__dict__.copy()
        leave_request.status = approval.status
        leave_request.approved_by = current_user.user_id
        leave_request.approved_at = datetime.now(timezone.utc)
        leave_request.comments = approval.comments
        leave_request.updated_at = datetime.now(timezone.utc)

        if approval.status == LeaveRequestStatus.APPROVED:
            query = select(LeaveBalances).where(
                LeaveBalances.user_id == leave_request.user_id,
                LeaveBalances.leave_type == leave_request.leave_type,
                LeaveBalances.is_active.is_(True),
                LeaveBalances.deleted_at.is_(None)
            )
            result = await db.execute(query)
            leave_balance = result.scalar_one_or_none()
            if not leave_balance:
                raise LeaveBalanceNotFoundError(user_id=leave_request.user_id, leave_type=leave_request.leave_type)
            available_days = leave_balance.allocated_days - leave_balance.used_days + leave_balance.carried_forward
            if leave_request.days_requested > available_days:
                raise ValidationError(detail="Insufficient leave balance")
            leave_balance.used_days += leave_request.days_requested
            leave_balance.updated_at = datetime.now(timezone.utc)
            db.add(leave_balance)

        db.add(leave_request)
        await db.commit()
        await db.refresh(leave_request)

        # Invalidate cache
        await invalidate_cache_prefix("leave_requests")
        logger.debug(f"Cache cleared for leave_requests")

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.APPROVE_LEAVE_REQUEST,
            table_affected="leave_requests",
            record_id=leave_id,
            old_values=old_values,
            new_values=leave_request.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        # Notify employee and admins
        query_user = select(Users).where(Users.user_id == leave_request.user_id)
        result_user = await db.execute(query_user)
        employee = result_user.scalar_one_or_none()
        query_admins = select(Users).where(Users.has_role(Permission.MANAGE_LEAVE))
        result_admins = await db.execute(query_admins)
        admins = result_admins.scalars().all()
        recipients = [(employee.email, employee.first_name)] + [(admin.email, admin.first_name) for admin in admins]
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"Leave Request {approval.status.value.capitalize()} (ID: {leave_request.leave_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"The leave request (ID: {leave_request.leave_id}) has been {approval.status.value.lower()}.\n"
                    f"Details:\n"
                    f"Leave Type: {leave_request.leave_type.value.capitalize()}\n"
                    f"Start Date: {leave_request.start_date}\n"
                    f"End Date: {leave_request.end_date}\n"
                    f"Comments: {approval.comments or 'None'}\n\n"
                    f"Please contact HR for any questions.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        logger.info(
            f"Leave request {leave_id} {approval.status.value} by user_id: {current_user.user_id}",
            extra={"request_id": request_id}
        )
        return LeaveRequestOut.model_validate(leave_request)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except LeaveRequestNotFoundError as e:
        logger.error(f"Leave request not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except LeaveBalanceNotFoundError as e:
        logger.error(f"Leave balance not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error approving leave request {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing leave request")

async def delete_leave_request(
    leave_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.DELETE_LEAVE_REQUEST]))
) -> None:
    """Soft delete a leave request with logging and notification."""
    try:
        if leave_id <= 0:
            raise ValidationError(detail="Invalid leave_id")

        await validate_leave_request_exists(db, leave_id, request_id)

        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == leave_id,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_leave_request = result.scalar_one_or_none()
        if not db_leave_request:
            raise LeaveRequestNotFoundError(leave_id=leave_id)

        db_leave_request.is_active = False
        db_leave_request.deleted_at = datetime.now(timezone.utc)
        db_leave_request.updated_at = datetime.now(timezone.utc)
        db.add(db_leave_request)
        await db.commit()

        # Invalidate cache
        await invalidate_cache_prefix("leave_requests")
        logger.debug(f"Cache cleared for leave_requests")

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_LEAVE_REQUEST,
            table_affected="leave_requests",
            record_id=leave_id,
            old_values=db_leave_request.__dict__,
            new_values=None,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        # Notify employee and admins
        query_user = select(Users).where(Users.user_id == db_leave_request.user_id)
        result_user = await db.execute(query_user)
        employee = result_user.scalar_one_or_none()
        query_admins = select(Users).where(Users.has_role(Permission.MANAGE_LEAVE))
        result_admins = await db.execute(query_admins)
        admins = result_admins.scalars().all()
        recipients = [(employee.email, employee.first_name)] + [(admin.email, admin.first_name) for admin in admins]
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"Leave Request Deleted (ID: {db_leave_request.leave_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"The leave request (ID: {db_leave_request.leave_id}) has been deleted.\n"
                    f"Details:\n"
                    f"Leave Type: {db_leave_request.leave_type.value.capitalize()}\n"
                    f"Start Date: {db_leave_request.start_date}\n"
                    f"End Date: {db_leave_request.end_date}\n\n"
                    f"Please contact HR for any questions.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        logger.info(
            f"Leave request soft deleted, leave_id: {leave_id}, user_id: {current_user.user_id}",
            extra={"request_id": request_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except LeaveRequestNotFoundError as e:
        logger.error(f"Leave request not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error deleting leave request {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting leave request")