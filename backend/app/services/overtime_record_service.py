from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
from app.models.overtime_records import OvertimeRecords
from app.models.users import Users
from app.models.attendance_records import AttendanceRecords
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.holiday_calendar import HolidayCalendar
from app.schemas.overtime_record import OvertimeRecordCreate, OvertimeRecordUpdate, OvertimeRecordOut, OvertimeRecordApproval
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission, OvertimeStatus
from app.core.mail import send_email
from app.core.exceptions import UserNotFoundError, OvertimeRecordNotFoundError, ValidationError, AttendanceRecordNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions_dependency, invalidate_user_cache, get_user_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_user_exists
from app.core.utils import get_request_id, get_users_with_permission
from app.services.system_log_service import create_system_log
from app.schemas.system_log import SystemLogCreate
import logging

logger = logging.getLogger(__name__)

async def validate_attendance_record_exists(db: AsyncSession, attendance_id: int, request_id: Optional[str] = None) -> None:
    """Validate that an attendance record exists."""
    query = select(AttendanceRecords).where(
        AttendanceRecords.attendance_id == attendance_id,
        AttendanceRecords.is_active.is_(True),
        AttendanceRecords.deleted_at.is_(None)
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        logger.error(f"Attendance record not found: {attendance_id}", extra={"request_id": request_id})
        raise AttendanceRecordNotFoundError(attendance_id=attendance_id)

async def create_overtime_record(
    overtime: OvertimeRecordCreate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.CREATE_OVERTIME_RECORD]))
) -> OvertimeRecordOut:
    """Create an overtime record with validation, holiday checks, logging, and notifications."""
    try:
        if overtime.user_id <= 0 or overtime.attendance_id <= 0:
            raise ValidationError(detail="Invalid user_id or attendance_id")
        if overtime.overtime_hours <= 0:
            raise ValidationError(detail="Overtime hours must be positive")
        if overtime.overtime_rate and overtime.overtime_rate <= 0:
            raise ValidationError(detail="Overtime rate must be positive")
        if overtime.date > date.today():
            raise ValidationError(detail="Overtime date cannot be in the future")

        await validate_user_exists(db, overtime.user_id, request_id)
        await validate_attendance_record_exists(db, overtime.attendance_id, request_id)

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if not any(p in [Permission.MANAGE_OVERTIME.value, Permission.CREATE_ALL_OVERTIME.value] for p in user_permissions) and overtime.user_id != current_user.user_id:
            query_hierarchy = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == overtime.user_id,
                EmployeeHierarchy.supervisor_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result_hierarchy = await db.execute(query_hierarchy)
            if not result_hierarchy.scalar_one_or_none():
                raise ValidationError(detail="Not authorized to create overtime record for this user")

        # Check for holidays if enabled
        if settings.CHECK_HOLIDAYS_ON_OVERTIME:
            query_holiday = select(HolidayCalendar).where(
                HolidayCalendar.holiday_date == overtime.date,
                HolidayCalendar.is_active.is_(True),
                HolidayCalendar.deleted_at.is_(None)
            )
            result_holiday = await db.execute(query_holiday)
            if result_holiday.scalar_one_or_none():
                raise ValidationError(detail="Overtime not allowed on a holiday")

        # Validate attendance record
        query = select(AttendanceRecords).where(
            AttendanceRecords.attendance_id == overtime.attendance_id,
            AttendanceRecords.user_id == overtime.user_id,
            AttendanceRecords.date == overtime.date,
            AttendanceRecords.is_active.is_(True),
            AttendanceRecords.deleted_at.is_(None)
        )
        result = await db.execute(query)
        attendance = result.scalar_one_or_none()
        if not attendance:
            raise AttendanceRecordNotFoundError(detail=f"No attendance record found for user_id {overtime.user_id} on {overtime.date} with attendance_id {overtime.attendance_id}")

        # Validate overtime hours against attendance record
        if attendance.overtime_hours and overtime.overtime_hours > attendance.overtime_hours:
            raise ValidationError(detail=f"Overtime hours ({overtime.overtime_hours}) exceed recorded attendance overtime hours ({attendance.overtime_hours})")

        # Check for existing overtime record
        query = select(OvertimeRecords).where(
            OvertimeRecords.user_id == overtime.user_id,
            OvertimeRecords.date == overtime.date,
            OvertimeRecords.is_active.is_(True),
            OvertimeRecords.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ValidationError(detail="Overtime record already exists for this date")

        # Create overtime record
        overtime_rate = overtime.overtime_rate or settings.DEFAULT_OVERTIME_RATE or 1.5
        db_overtime = OvertimeRecords(
            attendance_id=overtime.attendance_id,
            user_id=overtime.user_id,
            date=overtime.date,
            overtime_hours=overtime.overtime_hours,
            overtime_rate=overtime_rate,
            overtime_amount=overtime.overtime_hours * overtime_rate,
            description=overtime.description,
            status=OvertimeStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_overtime)
        await db.commit()
        await db.refresh(db_overtime)

        # Notify employee and manager
        eat_tz = ZoneInfo("Africa/Nairobi")
        current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
        recipients = [(current_user.email, current_user.first_name)]
        query_manager = select(Users).join(
            EmployeeHierarchy,
            and_(
                EmployeeHierarchy.supervisor_id == Users.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
        ).where(
            EmployeeHierarchy.employee_id == overtime.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_manager = await db.execute(query_manager)
        manager = result_manager.scalar_one_or_none()
        if manager:
            recipients.append((manager.email, manager.first_name))
        if overtime.overtime_hours > settings.OVERTIME_THRESHOLD:
            for email, first_name in recipients:
                await send_email(
                    to_email=email,
                    subject=f"Overtime Record Created (ID: {db_overtime.overtime_id})",
                    body=(
                        f"Dear {first_name},\n\n"
                        f"An overtime record (ID: {db_overtime.overtime_id}) has been created for user ID {overtime.user_id}.\n"
                        f"Details:\n"
                        f"Overtime Hours: {overtime.overtime_hours}\n"
                        f"Threshold Exceeded: {settings.OVERTIME_THRESHOLD} hours\n"
                        f"Status: {db_overtime.status.value}\n"
                        f"Created At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                        f"Please review in the Employee Management System.\n\n"
                        f"Best regards,\nEmployee Management System"
                    ),
                    request_id=request_id
                )

        # Invalidate cache
        invalidate_user_cache(overtime.user_id)
        await invalidate_cache_prefix("overtime_records")
        logger.info(f"Cache invalidated for overtime_records and user_id: {overtime.user_id}", extra={"request_id": request_id})

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_OVERTIME_RECORD,
            table_affected="overtime_records",
            record_id=db_overtime.overtime_id,
            old_values=None,
            new_values=db_overtime.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Overtime record created, overtime_id: {db_overtime.overtime_id}, user_id: {overtime.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return OvertimeRecordOut.model_validate(db_overtime)

    except (UserNotFoundError, AttendanceRecordNotFoundError, ValidationError) as e:
        logger.error(f"Error creating overtime record: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY if isinstance(e, ValidationError) else status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating overtime record: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating overtime record")

async def get_overtime_record(
    overtime_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_OVERTIME_RECORD, Permission.VIEW_OWN_OVERTIME_RECORD]))
) -> OvertimeRecordOut:
    """Retrieve an overtime record by ID with caching and authorization."""
    try:
        if overtime_id <= 0:
            raise ValidationError(detail="Invalid overtime_id")

        cache_key = f"overtime_record:{overtime_id}"
        cached_record = await get_cache(cache_key)
        if cached_record:
            logger.info(f"Cache hit for overtime_record:{overtime_id}", extra={"request_id": request_id})
            return OvertimeRecordOut(**cached_record)

        query = select(OvertimeRecords).where(
            OvertimeRecords.overtime_id == overtime_id,
            OvertimeRecords.is_active.is_(True),
            OvertimeRecords.deleted_at.is_(None)
        )
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if not any(p in [Permission.VIEW_OVERTIME_RECORD.value, Permission.MANAGE_OVERTIME.value] for p in user_permissions):
            query = query.where(
                or_(
                    OvertimeRecords.user_id == current_user.user_id,
                    OvertimeRecords.user_id.in_(
                        select(EmployeeHierarchy.employee_id).where(
                            EmployeeHierarchy.supervisor_id == current_user.user_id,
                            EmployeeHierarchy.is_active.is_(True),
                            EmployeeHierarchy.deleted_at.is_(None)
                        )
                    )
                )
            )
        result = await db.execute(query)
        overtime = result.scalar_one_or_none()

        if not overtime:
            raise OvertimeRecordNotFoundError(overtime_id=overtime_id)

        record_dict = OvertimeRecordOut.model_validate(overtime).model_dump()
        await set_cache(cache_key, record_dict, ttl=300)
        logger.info(f"Cache set for overtime_record:{overtime_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved overtime record, overtime_id: {overtime_id}, user_id: {overtime.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return OvertimeRecordOut.model_validate(overtime)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except OvertimeRecordNotFoundError as e:
        logger.error(f"Overtime record not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving overtime record")

async def get_user_overtime_records(
    user_id: int,
    status: Optional[OvertimeStatus] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_OVERTIME_RECORD, Permission.VIEW_OWN_OVERTIME_RECORD]))
) -> List[OvertimeRecordOut]:
    """Retrieve a list of overtime records for a user with optional filters and pagination."""
    try:
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")
        if start_date and end_date and start_date > end_date:
            raise ValidationError(detail="Start date must be on or before end date")
        if user_id <= 0:
            raise ValidationError(detail="Invalid user_id")

        await validate_user_exists(db, user_id, request_id)

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if not any(p in [Permission.VIEW_OVERTIME_RECORD.value, Permission.MANAGE_OVERTIME.value] for p in user_permissions) and user_id != current_user.user_id:
            query_hierarchy = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == user_id,
                EmployeeHierarchy.supervisor_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result_hierarchy = await db.execute(query_hierarchy)
            if not result_hierarchy.scalar_one_or_none():
                raise ValidationError(detail="Not authorized to view overtime records for this user")

        cache_key = f"overtime_records_user:{user_id}:{status or 'all'}:{start_date or 'all'}:{end_date or 'all'}:{skip}:{limit or settings.DEFAULT_PAGE_SIZE}"
        cached_records = await get_cache(cache_key)
        if cached_records:
            logger.info(f"Cache hit for overtime_records_user:{user_id}", extra={"request_id": request_id})
            return [OvertimeRecordOut(**r) for r in cached_records]

        query = select(OvertimeRecords).where(
            OvertimeRecords.user_id == user_id,
            OvertimeRecords.is_active.is_(True),
            OvertimeRecords.deleted_at.is_(None)
        )
        if status:
            query = query.where(OvertimeRecords.status == status)
        if start_date:
            query = query.where(OvertimeRecords.date >= start_date)
        if end_date:
            query = query.where(OvertimeRecords.date <= end_date)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = query.order_by(OvertimeRecords.date.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        overtime_records = result.scalars().all()

        records_dict = [OvertimeRecordOut.model_validate(r).model_dump() for r in overtime_records]
        await set_cache(cache_key, records_dict, ttl=300)
        logger.info(f"Cache set for overtime_records_user:{user_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(overtime_records)} overtime records for user_id: {user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [OvertimeRecordOut.model_validate(record) for record in overtime_records]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving overtime records for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving overtime records")

async def get_team_overtime_records(
    status: Optional[OvertimeStatus] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_TEAM_OVERTIME_RECORDS]))
) -> List[OvertimeRecordOut]:
    """Retrieve overtime records for a manager's team with optional filters and pagination."""
    try:
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")
        if start_date and end_date and start_date > end_date:
            raise ValidationError(detail="Start date must be on or before end date")

        cache_key = f"overtime_records_team:{current_user.user_id}:{status or 'all'}:{start_date or 'all'}:{end_date or 'all'}:{skip}:{limit or settings.DEFAULT_PAGE_SIZE}"
        cached_records = await get_cache(cache_key)
        if cached_records:
            logger.info(f"Cache hit for overtime_records_team:{current_user.user_id}", extra={"request_id": request_id})
            return [OvertimeRecordOut(**r) for r in cached_records]

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

        query = select(OvertimeRecords).where(
            OvertimeRecords.user_id.in_(employee_ids),
            OvertimeRecords.is_active.is_(True),
            OvertimeRecords.deleted_at.is_(None)
        )
        if status:
            query = query.where(OvertimeRecords.status == status)
        if start_date:
            query = query.where(OvertimeRecords.date >= start_date)
        if end_date:
            query = query.where(OvertimeRecords.date <= end_date)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = query.order_by(OvertimeRecords.date.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        overtime_records = result.scalars().all()

        records_dict = [OvertimeRecordOut.model_validate(r).model_dump() for r in overtime_records]
        await set_cache(cache_key, records_dict, ttl=300)
        logger.info(f"Cache set for overtime_records_team:{current_user.user_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(overtime_records)} overtime records for supervisor_id: {current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [OvertimeRecordOut.model_validate(record) for record in overtime_records]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving team overtime records for supervisor_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving team overtime records")

async def update_overtime_record(
    overtime_id: int,
    overtime_update: OvertimeRecordUpdate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.UPDATE_OVERTIME]))
) -> OvertimeRecordOut:
    """Update an overtime record with validation, logging, and notifications."""
    try:
        if overtime_id <= 0:
            raise ValidationError(detail="Invalid overtime_id")
        if overtime_update.overtime_hours and overtime_update.overtime_hours <= 0:
            raise ValidationError(detail="Overtime hours must be positive")
        if overtime_update.overtime_rate and overtime_update.overtime_rate <= 0:
            raise ValidationError(detail="Overtime rate must be positive")
        if overtime_update.date and overtime_update.date > date.today():
            raise ValidationError(detail="Overtime date cannot be in the future")

        query = select(OvertimeRecords).where(
            OvertimeRecords.overtime_id == overtime_id,
            OvertimeRecords.is_active.is_(True),
            OvertimeRecords.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_overtime = result.scalar_one_or_none()

        if not db_overtime:
            raise OvertimeRecordNotFoundError(overtime_id=overtime_id)

        update_data = overtime_update.model_dump(exclude_none=True)
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        if "user_id" in update_data:
            await validate_user_exists(db, update_data["user_id"], request_id)
        if "approved_by" in update_data and update_data["approved_by"] is not None:
            await validate_user_exists(db, update_data["approved_by"], request_id)
        if "attendance_id" in update_data:
            await validate_attendance_record_exists(db, update_data["attendance_id"], request_id)
            query_attendance = select(AttendanceRecords).where(
                AttendanceRecords.attendance_id == update_data["attendance_id"],
                AttendanceRecords.user_id == (update_data.get("user_id", db_overtime.user_id)),
                AttendanceRecords.date == (update_data.get("date", db_overtime.date)),
                AttendanceRecords.is_active.is_(True),
                AttendanceRecords.deleted_at.is_(None)
            )
            result_attendance = await db.execute(query_attendance)
            if not result_attendance.scalar_one_or_none():
                raise AttendanceRecordNotFoundError(detail=f"No attendance record found for user_id {update_data.get('user_id', db_overtime.user_id)} on {update_data.get('date', db_overtime.date)}")

        # Validate overtime hours against attendance record
        if "overtime_hours" in update_data or "attendance_id" in update_data or "user_id" in update_data or "date" in update_data:
            attendance_id = update_data.get("attendance_id", db_overtime.attendance_id)
            query_attendance = select(AttendanceRecords).where(
                AttendanceRecords.attendance_id == attendance_id,
                AttendanceRecords.is_active.is_(True),
                AttendanceRecords.deleted_at.is_(None)
            )
            result_attendance = await db.execute(query_attendance)
            attendance = result_attendance.scalar_one_or_none()
            if attendance and attendance.overtime_hours and update_data.get("overtime_hours", db_overtime.overtime_hours) > attendance.overtime_hours:
                raise ValidationError(detail=f"Overtime hours ({update_data.get('overtime_hours', db_overtime.overtime_hours)}) exceed recorded attendance overtime hours ({attendance.overtime_hours})")

        # Recalculate overtime amount
        if update_data.get("overtime_hours") or update_data.get("overtime_rate"):
            hours = update_data.get("overtime_hours", db_overtime.overtime_hours)
            rate = update_data.get("overtime_rate", db_overtime.overtime_rate)
            update_data["overtime_amount"] = hours * rate

        old_values = db_overtime.__dict__.copy()
        for key, value in update_data.items():
            setattr(db_overtime, key, value)

        db_overtime.updated_at = datetime.now(timezone.utc)
        db.add(db_overtime)
        await db.commit()
        await db.refresh(db_overtime)

        # Notify employee and manager if significant changes
        eat_tz = ZoneInfo("Africa/Nairobi")
        current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
        if any(key in update_data for key in ["overtime_hours", "overtime_rate", "date", "user_id", "attendance_id"]):
            recipients = []
            query_employee = select(Users).where(
                Users.user_id == db_overtime.user_id,
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
                EmployeeHierarchy.employee_id == db_overtime.user_id,
                Users.is_active.is_(True),
                Users.deleted_at.is_(None)
            )
            result_manager = await db.execute(query_manager)
            manager = result_manager.scalar_one_or_none()
            if manager:
                recipients.append((manager.email, manager.first_name))
            for email, first_name in recipients:
                await send_email(
                    to_email=email,
                    subject=f"Overtime Record Updated (ID: {db_overtime.overtime_id})",
                    body=(
                        f"Dear {first_name},\n\n"
                        f"The overtime record (ID: {db_overtime.overtime_id}) for user ID {db_overtime.user_id} has been updated.\n"
                        f"Details:\n"
                        f"Date: {db_overtime.date}\n"
                        f"Overtime Hours: {db_overtime.overtime_hours}\n"
                        f"Status: {db_overtime.status.value}\n"
                        f"Updated At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                        f"Please review in the Employee Management System.\n\n"
                        f"Best regards,\nEmployee Management System"
                    ),
                    request_id=request_id
                )

        # Invalidate cache
        invalidate_user_cache(db_overtime.user_id)
        await invalidate_cache_prefix("overtime_records")
        logger.info(f"Cache invalidated for overtime_records and user_id: {db_overtime.user_id}", extra={"request_id": request_id})

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_OVERTIME_RECORD,
            table_affected="overtime_records",
            record_id=overtime_id,
            old_values=old_values,
            new_values=db_overtime.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Overtime record updated, overtime_id: {overtime_id}, user_id: {db_overtime.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return OvertimeRecordOut.model_validate(db_overtime)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (OvertimeRecordNotFoundError, UserNotFoundError, AttendanceRecordNotFoundError) as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error updating overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating overtime record")

async def approve_overtime_record(
    record_id: int,
    approval: OvertimeRecordApproval,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.APPROVE_OVERTIME]))
) -> OvertimeRecordOut:
    """Approve or reject an overtime record with validation, logging, and notifications."""
    try:
        if record_id <= 0:
            raise ValidationError(detail="Invalid overtime_id")

        query = select(OvertimeRecords).where(
            OvertimeRecords.overtime_id == record_id,
            OvertimeRecords.is_active.is_(True),
            OvertimeRecords.deleted_at.is_(None)
        )
        result = await db.execute(query)
        overtime = result.scalar_one_or_none()
        if not overtime:
            raise OvertimeRecordNotFoundError(overtime_id=record_id)

        # Prevent re-approval/rejection
        if overtime.status != OvertimeStatus.PENDING:
            raise ValidationError(detail=f"Overtime record is already {overtime.status.value.lower()}")

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if not any(p == Permission.MANAGE_OVERTIME.value for p in user_permissions):
            query_hierarchy = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == overtime.user_id,
                EmployeeHierarchy.supervisor_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result_hierarchy = await db.execute(query_hierarchy)
            if not result_hierarchy.scalar_one_or_none():
                raise ValidationError(detail="Not authorized to approve this overtime record")

        old_values = overtime.__dict__.copy()
        overtime.status = approval.status
        overtime.approved_by = current_user.user_id
        overtime.approved_at = datetime.now(timezone.utc)
        overtime.comments = approval.comments
        overtime.updated_at = datetime.now(timezone.utc)

        db.add(overtime)
        await db.commit()
        await db.refresh(overtime)

        # Notify employee and admins
        eat_tz = ZoneInfo("Africa/Nairobi")
        current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
        recipients = []
        query_employee = select(Users).where(
            Users.user_id == overtime.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_employee = await db.execute(query_employee)
        employee = result_employee.scalar_one_or_none()
        if employee:
            recipients.append((employee.email, employee.first_name))
        admins = await get_users_with_permission(Permission.MANAGE_OVERTIME, db)
        recipients.extend([(admin.email, admin.first_name) for admin in admins])
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"Overtime Record {approval.status.value.capitalize()} (ID: {overtime.overtime_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"The overtime record (ID: {overtime.overtime_id}) for user ID {overtime.user_id} has been {approval.status.value.lower()}.\n"
                    f"Details:\n"
                    f"Date: {overtime.date}\n"
                    f"Overtime Hours: {overtime.overtime_hours}\n"
                    f"Comments: {approval.comments or 'None'}\n"
                    f"Approved At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        # Invalidate cache
        invalidate_user_cache(overtime.user_id)
        await invalidate_cache_prefix("overtime_records")
        logger.info(f"Cache invalidated for overtime_records and user_id: {overtime.user_id}", extra={"request_id": request_id})

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.APPROVE_OVERTIME_RECORD,
            table_affected="overtime_records",
            record_id=overtime.overtime_id,
            old_values=old_values,
            new_values=overtime.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Overtime record {record_id} {approval.status.value} by user_id: {current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return OvertimeRecordOut.model_validate(overtime)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except OvertimeRecordNotFoundError as e:
        logger.error(f"Overtime record not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error approving overtime record {record_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing overtime record")

async def delete_overtime_record(
    overtime_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.DELETE_OVERTIME]))
) -> None:
    """Soft delete an overtime record with validation, logging, and notifications."""
    try:
        if overtime_id <= 0:
            raise ValidationError(detail="Invalid overtime_id")

        query = select(OvertimeRecords).where(
            OvertimeRecords.overtime_id == overtime_id,
            OvertimeRecords.is_active.is_(True),
            OvertimeRecords.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_overtime = result.scalar_one_or_none()

        if not db_overtime:
            raise OvertimeRecordNotFoundError(overtime_id=overtime_id)

        # Prevent deletion of approved records if configured
        if settings.PREVENT_DELETE_APPROVED_OVERTIME and db_overtime.status == OvertimeStatus.APPROVED:
            raise ValidationError(detail="Cannot delete approved overtime record")

        db_overtime.is_active = False
        db_overtime.deleted_at = datetime.now(timezone.utc)
        db_overtime.updated_at = datetime.now(timezone.utc)
        db.add(db_overtime)
        await db.commit()

        # Notify employee and admins
        eat_tz = ZoneInfo("Africa/Nairobi")
        current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
        recipients = []
        query_employee = select(Users).where(
            Users.user_id == db_overtime.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result_employee = await db.execute(query_employee)
        employee = result_employee.scalar_one_or_none()
        if employee:
            recipients.append((employee.email, employee.first_name))
        admins = await get_users_with_permission(Permission.MANAGE_OVERTIME, db)
        recipients.extend([(admin.email, admin.first_name) for admin in admins])
        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"Overtime Record Deleted (ID: {db_overtime.overtime_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"The overtime record (ID: {db_overtime.overtime_id}) for user ID {db_overtime.user_id} has been deleted.\n"
                    f"Details:\n"
                    f"Date: {db_overtime.date}\n"
                    f"Overtime Hours: {db_overtime.overtime_hours}\n"
                    f"Deleted At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                    f"Please contact HR for any questions.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

        # Invalidate cache
        invalidate_user_cache(db_overtime.user_id)
        await invalidate_cache_prefix("overtime_records")
        logger.info(f"Cache invalidated for overtime_records and user_id: {db_overtime.user_id}", extra={"request_id": request_id})

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_OVERTIME_RECORD,
            table_affected="overtime_records",
            record_id=overtime_id,
            old_values=db_overtime.__dict__,
            new_values=None,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Overtime record soft deleted, overtime_id: {overtime_id}, user_id: {db_overtime.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except OvertimeRecordNotFoundError as e:
        logger.error(f"Overtime record not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error deleting overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting overtime record")