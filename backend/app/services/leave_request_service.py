from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from app.models.leave_requests import LeaveRequests
from app.models.users import Users
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.leave_balances import LeaveBalances
from app.models.holiday_calendar import HolidayCalendar
from app.models.leave_policies import LeavePolicies
from app.schemas.leave_request import LeaveRequestCreate, LeaveRequestUpdate, LeaveRequestOut, LeaveApprovalUpdate
from app.schemas.system_log import SystemLogCreate
from app.core.config import Settings, get_settings
from app.core.enums import LeaveRequestStatus, SystemAction, Permission, LeaveType
from app.core.mail import send_email
from app.core.exceptions import LeaveRequestNotFoundError, LeaveBalanceNotFoundError, ValidationError
from app.core.security import get_current_user
from app.core.permissions import require_permissions_dependency, invalidate_user_cache, get_user_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_leave_request_exists, validate_user_exists
from app.core.utils import get_request_id, get_users_with_permission
from app.services.system_log_service import create_system_log
import logging

logger = logging.getLogger(__name__)

async def validate_no_overlapping_leave_requests(
    db: AsyncSession,
    user_id: int,
    start_date: date,
    end_date: date,
    leave_id: Optional[int] = None,
    request_id: Optional[str] = None,
    settings: Settings = Depends(get_settings)
) -> None:
    """Validate that no overlapping leave requests or holidays exist."""
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

    # Check for holidays if enabled
    if settings.CHECK_HOLIDAYS_ON_LEAVE:
        query_holiday = select(HolidayCalendar).where(
            HolidayCalendar.holiday_date.between(start_date, end_date),
            HolidayCalendar.is_active.is_(True),
            HolidayCalendar.deleted_at.is_(None)
        )
        result_holiday = await db.execute(query_holiday)
        if result_holiday.scalars().first():
            raise ValidationError(detail="Leave request overlaps with a holiday")

async def create_leave_request(
    leave_request: LeaveRequestCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.CREATE_LEAVE_REQUEST]))
) -> LeaveRequestOut:
    """Create a new leave request with validation, holiday checks, policy checks, logging, and notifications."""
    try:
        if leave_request.user_id <= 0:
            raise ValidationError(detail="Invalid user_id")
        if leave_request.start_date < date.today():
            raise ValidationError(detail="Start date cannot be in the past")
        if leave_request.end_date < leave_request.start_date:
            raise ValidationError(detail="End date must be on or after start date")
        if leave_request.leave_type not in LeaveType:
            raise ValidationError(detail=f"Invalid leave type: {leave_request.leave_type}")

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if not any(p in [Permission.MANAGE_LEAVE.value, Permission.CREATE_ALL_LEAVE_REQUESTS.value] for p in user_permissions) and leave_request.user_id != current_user.user_id:
            query_hierarchy = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == leave_request.user_id,
                EmployeeHierarchy.supervisor_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result_hierarchy = await db.execute(query_hierarchy)
            if not result_hierarchy.scalar_one_or_none():
                raise ValidationError(detail="Not authorized to create leave request for this user")

        await validate_user_exists(db, leave_request.user_id, request_id)
        await validate_no_overlapping_leave_requests(db, leave_request.user_id, leave_request.start_date, leave_request.end_date, request_id=request_id, settings=settings)

        # Validate leave balance
        query_balance = select(LeaveBalances).where(
            LeaveBalances.user_id == leave_request.user_id,
            LeaveBalances.leave_type == leave_request.leave_type,
            LeaveBalances.is_active.is_(True),
            LeaveBalances.deleted_at.is_(None)
        )
        result_balance = await db.execute(query_balance)
        leave_balance = result_balance.scalar_one_or_none()
        if not leave_balance:
            logger.debug(
                f"No leave balance found for user_id: {leave_request.user_id}, leave_type: {leave_request.leave_type}",
                extra={"request_id": request_id}
            )
            raise LeaveBalanceNotFoundError(user_id=leave_request.user_id, leave_type=leave_request.leave_type)

        days_requested = (leave_request.end_date - leave_request.start_date).days + 1
        available_days = leave_balance.allocated_days - leave_balance.used_days + leave_balance.carried_forward
        if days_requested > available_days:
            raise ValidationError(detail=f"Insufficient leave balance: {available_days} days available, {days_requested} days requested")

        # Validate against leave policy
        query_policy = select(LeavePolicies).where(
            LeavePolicies.leave_type == leave_request.leave_type,
            LeavePolicies.is_active.is_(True),
            LeavePolicies.deleted_at.is_(None)
        )
        result_policy = await db.execute(query_policy)
        leave_policy = result_policy.scalar_one_or_none()
        if leave_policy and days_requested > leave_policy.max_consecutive_days:
            raise ValidationError(detail=f"Requested days ({days_requested}) exceed policy limit ({leave_policy.max_consecutive_days}) for {leave_request.leave_type.value}")

        # Create leave request
        db_leave_request = LeaveRequests(
            user_id=leave_request.user_id,
            leave_type=leave_request.leave_type,
            start_date=leave_request.start_date,
            end_date=leave_request.end_date,
            days_requested=days_requested,
            reason=leave_request.reason,
            status=LeaveRequestStatus.UNDER_REVIEW,
            attachment_url=str(leave_request.attachment_url) if leave_request.attachment_url else None,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_leave_request)
        await db.commit()
        await db.refresh(db_leave_request)

        # Notify employee, manager, and admins
        eat_tz = ZoneInfo("Africa/Nairobi")
        current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
        recipients = []
        query_employee = select(Users).where(
            Users.user_id == leave_request.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_employee = await db.execute(query_employee)
        employee = result_employee.scalar_one_or_none()
        if employee:
            recipients.append((employee.email, employee.first_name))
        query_manager = select(Users).join(
            EmployeeHierarchy,
            and_(
                EmployeeHierarchy.supervisor_id == Users.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
        ).where(
            EmployeeHierarchy.employee_id == leave_request.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_manager = await db.execute(query_manager)
        manager = result_manager.scalar_one_or_none()
        if manager:
            recipients.append((manager.email, manager.first_name))
        admins = await get_users_with_permission(Permission.MANAGE_LEAVE, db)
        recipients.extend([(admin.email, admin.first_name) for admin in admins])
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"New Leave Request Submitted (ID: {db_leave_request.leave_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"Employee {employee.first_name if employee else 'Unknown'} {employee.last_name if employee else ''} submitted a leave request.\n"
                    f"Details:\n"
                    f"Leave Type: {leave_request.leave_type.value.capitalize()}\n"
                    f"Start Date: {leave_request.start_date}\n"
                    f"End Date: {leave_request.end_date}\n"
                    f"Days Requested: {days_requested}\n"
                    f"Reason: {leave_request.reason or 'None'}\n"
                    f"Created At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        # Invalidate cache
        invalidate_user_cache(leave_request.user_id)
        await invalidate_cache_prefix("leave_requests")
        logger.info(f"Cache invalidated for leave_requests and user_id: {leave_request.user_id}", extra={"request_id": request_id})

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

        logger.info(
            f"Leave request created, leave_id: {db_leave_request.leave_id}, user_id: {leave_request.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return LeaveRequestOut.model_validate(db_leave_request)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except LeaveBalanceNotFoundError as e:
        logger.error(f"Leave balance not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating leave request for user_id {leave_request.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating leave request")

async def get_leave_request(
    leave_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_LEAVE_REQUEST, Permission.VIEW_OWN_LEAVE_REQUEST]))
) -> LeaveRequestOut:
    """Retrieve a leave request by ID with caching and authorization."""
    try:
        if leave_id <= 0:
            raise ValidationError(detail="Invalid leave_id")

        cache_key = f"leave_request:{leave_id}"
        cached_request = await get_cache(cache_key)
        if cached_request:
            logger.info(f"Cache hit for leave_request:{leave_id}", extra={"request_id": request_id})
            return LeaveRequestOut(**cached_request)

        await validate_leave_request_exists(db, leave_id, request_id)

        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == leave_id,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if not any(p in [Permission.VIEW_LEAVE_REQUEST.value, Permission.MANAGE_LEAVE.value] for p in user_permissions):
            query = query.where(
                or_(
                    LeaveRequests.user_id == current_user.user_id,
                    LeaveRequests.user_id.in_(
                        select(EmployeeHierarchy.employee_id).where(
                            EmployeeHierarchy.supervisor_id == current_user.user_id,
                            EmployeeHierarchy.is_active.is_(True),
                            EmployeeHierarchy.deleted_at.is_(None)
                        )
                    )
                )
            )
        result = await db.execute(query)
        leave_request = result.scalar_one_or_none()

        if not leave_request:
            raise LeaveRequestNotFoundError(leave_id=leave_id)

        leave_request_dict = LeaveRequestOut.model_validate(leave_request).model_dump()
        await set_cache(cache_key, leave_request_dict, ttl=300)
        logger.info(f"Cache set for leave_request:{leave_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved leave request, leave_id: {leave_id}, user_id: {leave_request.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
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
    status: Optional[LeaveRequestStatus] = None,
    leave_type: Optional[LeaveType] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_LEAVE_REQUEST, Permission.VIEW_OWN_LEAVE_REQUEST]))
) -> List[LeaveRequestOut]:
    """Retrieve a list of leave requests with optional filters and pagination."""
    try:
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")
        if user_id is not None and user_id <= 0:
            raise ValidationError(detail="Invalid user_id")
        if leave_type is not None and leave_type not in LeaveType:
            raise ValidationError(detail=f"Invalid leave type: {leave_type}")

        cache_key = f"leave_requests:{user_id or 'all'}:{status or 'all'}:{leave_type or 'all'}:{skip}:{limit or settings.DEFAULT_PAGE_SIZE}"
        cached_requests = await get_cache(cache_key)
        if cached_requests:
            logger.info(f"Cache hit for leave_requests:{user_id or 'all'}", extra={"request_id": request_id})
            return [LeaveRequestOut(**req) for req in cached_requests]

        query = select(LeaveRequests).where(
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        if user_id:
            await validate_user_exists(db, user_id, request_id)
            query = query.where(LeaveRequests.user_id == user_id)
        if status:
            query = query.where(LeaveRequests.status == status)
        if leave_type:
            query = query.where(LeaveRequests.leave_type == leave_type)
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if not any(p in [Permission.VIEW_LEAVE_REQUEST.value, Permission.MANAGE_LEAVE.value] for p in user_permissions):
            query = query.where(
                or_(
                    LeaveRequests.user_id == current_user.user_id,
                    LeaveRequests.user_id.in_(
                        select(EmployeeHierarchy.employee_id).where(
                            EmployeeHierarchy.supervisor_id == current_user.user_id,
                            EmployeeHierarchy.is_active.is_(True),
                            EmployeeHierarchy.deleted_at.is_(None)
                        )
                    )
                )
            )
        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = query.order_by(LeaveRequests.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        leave_requests = result.scalars().all()

        leave_requests_dict = [LeaveRequestOut.model_validate(req).model_dump() for req in leave_requests]
        await set_cache(cache_key, leave_requests_dict, ttl=300)
        logger.info(f"Cache set for leave_requests:{user_id or 'all'}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(leave_requests)} leave requests for user_id: {user_id or 'all'}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [LeaveRequestOut.model_validate(req) for req in leave_requests]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving leave requests for user_id {user_id or 'all'}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave requests")

async def update_leave_request(
    leave_id: int,
    leave_request_update: LeaveRequestUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.UPDATE_LEAVE_REQUEST]))
) -> LeaveRequestOut:
    """Update a leave request with validation, policy checks, logging, and notifications."""
    try:
        if leave_id <= 0:
            raise ValidationError(detail="Invalid leave_id")
        if leave_request_update.start_date and leave_request_update.start_date < date.today():
            raise ValidationError(detail="Start date cannot be in the past")
        if leave_request_update.start_date and leave_request_update.end_date and leave_request_update.end_date < leave_request_update.start_date:
            raise ValidationError(detail="End date must be on or after start date")
        if leave_request_update.leave_type and leave_request_update.leave_type not in LeaveType:
            raise ValidationError(detail=f"Invalid leave type: {leave_request_update.leave_type}")

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

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if not any(p == Permission.MANAGE_LEAVE.value for p in user_permissions) and db_leave_request.user_id != current_user.user_id:
            query_hierarchy = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == db_leave_request.user_id,
                EmployeeHierarchy.supervisor_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result_hierarchy = await db.execute(query_hierarchy)
            if not result_hierarchy.scalar_one_or_none():
                raise ValidationError(detail="Not authorized to update this leave request")

        update_data = leave_request_update.model_dump(exclude_none=True)
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        # Validate user_id if updated
        if "user_id" in update_data:
            await validate_user_exists(db, update_data["user_id"], request_id)

        # Validate leave balance and policy if leave_type, start_date, or end_date are updated
        if any(k in update_data for k in ["leave_type", "start_date", "end_date"]):
            leave_type = update_data.get("leave_type", db_leave_request.leave_type)
            start_date = update_data.get("start_date", db_leave_request.start_date)
            end_date = update_data.get("end_date", db_leave_request.end_date)
            days_requested = (end_date - start_date).days + 1
            user_id = update_data.get("user_id", db_leave_request.user_id)

            query_balance = select(LeaveBalances).where(
                LeaveBalances.user_id == user_id,
                LeaveBalances.leave_type == leave_type,
                LeaveBalances.is_active.is_(True),
                LeaveBalances.deleted_at.is_(None)
            )
            result_balance = await db.execute(query_balance)
            leave_balance = result_balance.scalar_one_or_none()
            if not leave_balance:
                logger.debug(
                    f"No leave balance found for user_id: {user_id}, leave_type: {leave_type}",
                    extra={"request_id": request_id}
                )
                raise LeaveBalanceNotFoundError(user_id=user_id, leave_type=leave_type)
            available_days = leave_balance.allocated_days - leave_balance.used_days + leave_balance.carried_forward
            if days_requested > available_days:
                raise ValidationError(detail=f"Insufficient leave balance: {available_days} days available, {days_requested} days requested")

            query_policy = select(LeavePolicies).where(
                LeavePolicies.leave_type == leave_type,
                LeavePolicies.is_active.is_(True),
                LeavePolicies.deleted_at.is_(None)
            )
            result_policy = await db.execute(query_policy)
            leave_policy = result_policy.scalar_one_or_none()
            if leave_policy and days_requested > leave_policy.max_consecutive_days:
                raise ValidationError(detail=f"Requested days ({days_requested}) exceed policy limit ({leave_policy.max_consecutive_days}) for {leave_type.value}")

            await validate_no_overlapping_leave_requests(db, user_id, start_date, end_date, leave_id, request_id, settings)
            update_data["days_requested"] = days_requested

        old_values = db_leave_request.__dict__.copy()
        for key, value in update_data.items():
            setattr(db_leave_request, key, value)
        db_leave_request.updated_at = datetime.now(timezone.utc)
        db.add(db_leave_request)
        await db.commit()
        await db.refresh(db_leave_request)

        # Notify employee, manager, and admins
        eat_tz = ZoneInfo("Africa/Nairobi")
        current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
        recipients = []
        query_employee = select(Users).where(
            Users.user_id == db_leave_request.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_employee = await db.execute(query_employee)
        employee = result_employee.scalar_one_or_none()
        if employee:
            recipients.append((employee.email, employee.first_name))
        query_manager = select(Users).join(
            EmployeeHierarchy,
            and_(
                EmployeeHierarchy.supervisor_id == Users.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
        ).where(
            EmployeeHierarchy.employee_id == db_leave_request.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_manager = await db.execute(query_manager)
        manager = result_manager.scalar_one_or_none()
        if manager:
            recipients.append((manager.email, manager.first_name))
        admins = await get_users_with_permission(Permission.MANAGE_LEAVE, db)
        recipients.extend([(admin.email, admin.first_name) for admin in admins])
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"Leave Request Updated (ID: {db_leave_request.leave_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"The leave request (ID: {db_leave_request.leave_id}) for user ID {db_leave_request.user_id} has been updated.\n"
                    f"Details:\n"
                    f"Leave Type: {db_leave_request.leave_type.value.capitalize()}\n"
                    f"Start Date: {db_leave_request.start_date}\n"
                    f"End Date: {db_leave_request.end_date}\n"
                    f"Days Requested: {db_leave_request.days_requested}\n"
                    f"Reason: {db_leave_request.reason or 'None'}\n"
                    f"Updated At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        # Invalidate cache
        invalidate_user_cache(db_leave_request.user_id)
        await invalidate_cache_prefix("leave_requests")
        logger.info(f"Cache invalidated for leave_requests and user_id: {db_leave_request.user_id}", extra={"request_id": request_id})

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

        logger.info(
            f"Leave request updated, leave_id: {leave_id}, user_id: {db_leave_request.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return LeaveRequestOut.model_validate(db_leave_request)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (LeaveRequestNotFoundError, LeaveBalanceNotFoundError) as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
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
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.APPROVE_LEAVE]))
) -> LeaveRequestOut:
    """Approve or reject a leave request, update balance, log, and notify."""
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

        # Prevent re-approval/rejection
        if leave_request.status != LeaveRequestStatus.UNDER_REVIEW:
            raise ValidationError(detail=f"Leave request is already {leave_request.status.value.lower()}")

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if not any(p == Permission.MANAGE_LEAVE.value for p in user_permissions):
            query_hierarchy = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == leave_request.user_id,
                EmployeeHierarchy.supervisor_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result_hierarchy = await db.execute(query_hierarchy)
            if not result_hierarchy.scalar_one_or_none():
                raise ValidationError(detail="Not authorized to approve this leave request")

        old_values = leave_request.__dict__.copy()
        leave_request.status = approval.status
        leave_request.approved_by = current_user.user_id
        leave_request.approved_at = datetime.now(timezone.utc)
        leave_request.comments = approval.comments
        leave_request.updated_at = datetime.now(timezone.utc)

        if approval.status == LeaveRequestStatus.APPROVED:
            query_balance = select(LeaveBalances).where(
                LeaveBalances.user_id == leave_request.user_id,
                LeaveBalances.leave_type == leave_request.leave_type,
                LeaveBalances.is_active.is_(True),
                LeaveBalances.deleted_at.is_(None)
            )
            result_balance = await db.execute(query_balance)
            leave_balance = result_balance.scalar_one_or_none()
            if not leave_balance:
                logger.debug(
                    f"No leave balance found for user_id: {leave_request.user_id}, leave_type: {leave_request.leave_type}",
                    extra={"request_id": request_id}
                )
                raise LeaveBalanceNotFoundError(user_id=leave_request.user_id, leave_type=leave_request.leave_type)
            available_days = leave_balance.allocated_days - leave_balance.used_days + leave_balance.carried_forward
            if leave_request.days_requested > available_days:
                raise ValidationError(detail=f"Insufficient leave balance: {available_days} days available, {leave_request.days_requested} days requested")
            leave_balance.used_days += leave_request.days_requested
            leave_balance.updated_at = datetime.now(timezone.utc)
            db.add(leave_balance)

        db.add(leave_request)
        await db.commit()
        await db.refresh(leave_request)

        # Notify employee, manager, and admins
        eat_tz = ZoneInfo("Africa/Nairobi")
        current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
        recipients = []
        query_employee = select(Users).where(
            Users.user_id == leave_request.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_employee = await db.execute(query_employee)
        employee = result_employee.scalar_one_or_none()
        if employee:
            recipients.append((employee.email, employee.first_name))
        query_manager = select(Users).join(
            EmployeeHierarchy,
            and_(
                EmployeeHierarchy.supervisor_id == Users.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
        ).where(
            EmployeeHierarchy.employee_id == leave_request.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_manager = await db.execute(query_manager)
        manager = result_manager.scalar_one_or_none()
        if manager:
            recipients.append((manager.email, manager.first_name))
        admins = await get_users_with_permission(Permission.MANAGE_LEAVE, db)
        recipients.extend([(admin.email, admin.first_name) for admin in admins])
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"Leave Request {approval.status.value.capitalize()} (ID: {leave_request.leave_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"The leave request (ID: {leave_request.leave_id}) for user ID {leave_request.user_id} has been {approval.status.value.lower()}.\n"
                    f"Details:\n"
                    f"Leave Type: {leave_request.leave_type.value.capitalize()}\n"
                    f"Start Date: {leave_request.start_date}\n"
                    f"End Date: {leave_request.end_date}\n"
                    f"Days Requested: {leave_request.days_requested}\n"
                    f"Comments: {approval.comments or 'None'}\n"
                    f"Approved At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        # Invalidate cache
        invalidate_user_cache(leave_request.user_id)
        await invalidate_cache_prefix("leave_requests")
        logger.info(f"Cache invalidated for leave_requests and user_id: {leave_request.user_id}", extra={"request_id": request_id})

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

        logger.info(
            f"Leave request {leave_id} {approval.status.value} by user_id: {current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return LeaveRequestOut.model_validate(leave_request)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (LeaveRequestNotFoundError, LeaveBalanceNotFoundError) as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error approving/rejecting leave request {leave_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing leave request")

async def get_team_leave_requests(
    status: Optional[LeaveRequestStatus] = None,
    leave_type: Optional[LeaveType] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_TEAM_LEAVE_REQUESTS]))
) -> List[LeaveRequestOut]:
    """Retrieve leave requests for a manager's team with optional filters and pagination."""
    try:
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")
        if start_date and end_date and start_date > end_date:
            raise ValidationError(detail="Start date must be on or before end date")
        if leave_type is not None and leave_type not in LeaveType:
            raise ValidationError(detail=f"Invalid leave type: {leave_type}")

        cache_key = f"leave_requests_team:{current_user.user_id}:{status or 'all'}:{leave_type or 'all'}:{start_date or 'all'}:{end_date or 'all'}:{skip}:{limit or settings.DEFAULT_PAGE_SIZE}"
        cached_requests = await get_cache(cache_key)
        if cached_requests:
            logger.info(f"Cache hit for leave_requests_team:{current_user.user_id}", extra={"request_id": request_id})
            return [LeaveRequestOut(**req) for req in cached_requests]

        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.supervisor_id == current_user.user_id,
            EmployeeHierarchy.is_active.is_(True),
            EmployeeHierarchy.deleted_at.is_(None)
        )
        result = await db.execute(query)
        team = result.scalars().all()
        employee_ids = [emp.employee_id for emp in team]

        if not employee_ids:
            return []

        query = select(LeaveRequests).where(
            LeaveRequests.user_id.in_(employee_ids),
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        if status:
            query = query.where(LeaveRequests.status == status)
        if leave_type:
            query = query.where(LeaveRequests.leave_type == leave_type)
        if start_date:
            query = query.where(LeaveRequests.start_date >= start_date)
        if end_date:
            query = query.where(LeaveRequests.end_date <= end_date)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = query.order_by(LeaveRequests.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        leave_requests = result.scalars().all()

        leave_requests_dict = [LeaveRequestOut.model_validate(req).model_dump() for req in leave_requests]
        await set_cache(cache_key, leave_requests_dict, ttl=300)
        logger.info(f"Cache set for leave_requests_team:{current_user.user_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(leave_requests)} leave requests for supervisor_id: {current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [LeaveRequestOut.model_validate(req) for req in leave_requests]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving team leave requests for supervisor_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving team leave requests")

async def delete_leave_request(
    leave_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.DELETE_LEAVE_REQUEST]))
) -> None:
    """Soft delete a leave request with validation, logging, and notifications."""
    try:
        if leave_id <= 0:
            raise ValidationError(detail="Invalid leave_id")

        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == leave_id,
            LeaveRequests.is_active.is_(True),
            LeaveRequests.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_leave_request = result.scalar_one_or_none()

        if not db_leave_request:
            raise LeaveRequestNotFoundError(leave_id=leave_id)

        # Prevent deletion of approved requests if configured
        if settings.PREVENT_DELETE_APPROVED_LEAVE and db_leave_request.status == LeaveRequestStatus.APPROVED:
            raise ValidationError(detail="Cannot delete approved leave request")

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if not any(p == Permission.MANAGE_LEAVE.value for p in user_permissions) and db_leave_request.user_id != current_user.user_id:
            query_hierarchy = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == db_leave_request.user_id,
                EmployeeHierarchy.supervisor_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result_hierarchy = await db.execute(query_hierarchy)
            if not result_hierarchy.scalar_one_or_none():
                raise ValidationError(detail="Not authorized to delete this leave request")

        db_leave_request.is_active = False
        db_leave_request.deleted_at = datetime.now(timezone.utc)
        db_leave_request.updated_at = datetime.now(timezone.utc)
        db.add(db_leave_request)
        await db.commit()

        # Notify employee and admins
        eat_tz = ZoneInfo("Africa/Nairobi")
        current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
        recipients = []
        query_employee = select(Users).where(
            Users.user_id == db_leave_request.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_employee = await db.execute(query_employee)
        employee = result_employee.scalar_one_or_none()
        if employee:
            recipients.append((employee.email, employee.first_name))
        admins = await get_users_with_permission(Permission.MANAGE_LEAVE, db)
        recipients.extend([(admin.email, admin.first_name) for admin in admins])
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"Leave Request Deleted (ID: {db_leave_request.leave_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"The leave request (ID: {db_leave_request.leave_id}) for user ID {db_leave_request.user_id} has been deleted.\n"
                    f"Details:\n"
                    f"Leave Type: {str(db_leave_request.leave_type).capitalize()}\n"
                    f"Start Date: {db_leave_request.start_date}\n"
                    f"End Date: {db_leave_request.end_date}\n"
                    f"Deleted At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                    f"Please contact HR for any questions.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        # Invalidate cache
        invalidate_user_cache(db_leave_request.user_id)
        await invalidate_cache_prefix("leave_requests")
        logger.info(f"Cache invalidated for leave_requests and user_id: {db_leave_request.user_id}", extra={"request_id": request_id})

        # Log the action
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

        logger.info(
            f"Leave request soft deleted, leave_id: {leave_id}, user_id: {db_leave_request.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
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