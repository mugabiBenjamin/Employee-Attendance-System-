from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select, and_
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
from app.models.attendance_records import AttendanceRecords
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.models.shift_assignments import ShiftAssignments
from app.models.shift_patterns import ShiftPatterns
from app.models.holiday_calendar import HolidayCalendar
from app.models.employee_hierarchy import EmployeeHierarchy
from app.schemas.attendance_record import AttendanceRecordCreate, AttendanceRecordOut
from app.core.config import Settings, get_settings
from app.core.utils import calculate_total_hours, calculate_overtime_hours, calculate_shift_hours
from app.core.enums import SystemAction, Permission
from app.core.security import get_current_user
from app.core.permissions import require_permissions_dependency, invalidate_user_cache, get_user_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.exceptions import UserNotFoundError, ValidationError, ResourceNotFoundError, AttendanceError
from app.core.utils import get_request_id, get_users_with_permission
from app.core.mail import send_email
import logging

logger = logging.getLogger(__name__)

async def clock_in(
    request: Request,
    user: Users = Depends(get_current_user),
    location: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.CLOCK_IN]))
) -> AttendanceRecordOut:
    """Handle employee clock-in with validation, holiday checks, and logging."""
    try:
        current_time = datetime.now(timezone.utc)
        current_date = current_time.date()
        eat_tz = ZoneInfo("Africa/Nairobi")  # EAT is UTC+3
        current_time_eat = current_time.astimezone(eat_tz)

        # Validate location if required
        if settings.REQUIRE_ATTENDANCE_LOCATION and (not location or location.strip() == ""):
            raise ValidationError(detail="Location is required for clock-in")
        if location and len(location) > 255:
            raise ValidationError(detail="Location exceeds maximum length")

        # Check for existing clock-in
        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == user.user_id,
            AttendanceRecords.date == current_date,
            AttendanceRecords.clock_out_time.is_(None),
            AttendanceRecords.is_active.is_(True),
            AttendanceRecords.deleted_at.is_(None)
        )
        result = await db.execute(query)
        existing_record = result.scalar_one_or_none()
        if existing_record:
            raise AttendanceError(detail="User already clocked in for today")

        # Check for holidays if enabled
        if settings.CHECK_HOLIDAYS_ON_ATTENDANCE:
            query_holiday = select(HolidayCalendar).where(
                HolidayCalendar.holiday_date == current_date,
                HolidayCalendar.is_active.is_(True),
                HolidayCalendar.deleted_at.is_(None)
            )
            result_holiday = await db.execute(query_holiday)
            if result_holiday.scalar_one_or_none():
                raise AttendanceError(detail="Clock-in not allowed on a holiday")

        # Validate IP address
        ip_address = str(request.client.host) if request.client and request.client.host else None
        if settings.REQUIRE_ATTENDANCE_IP and not ip_address:
            raise ValidationError(detail="IP address is required for clock-in")

        # Create attendance record with explicit transaction handling
        try:
            db_record = AttendanceRecords(
                **AttendanceRecordCreate(
                    user_id=user.user_id,
                    clock_in_time=current_time,
                    ip_address=ip_address,
                    location=location,
                    date=current_date
                ).model_dump(),
                created_at=current_time,
                updated_at=current_time,
            )
            db.add(db_record)
            await db.flush()  # Flush to get the ID before committing
            
            # Get admin users and send notifications BEFORE commit
            if settings.NOTIFY_ON_ATTENDANCE:
                admins = await get_users_with_permission(Permission.MANAGE_ATTENDANCE, db)
                recipients = [(user.email, user.first_name)]
                recipients.extend([(admin.email, admin.first_name) for admin in admins])
                for email, first_name in recipients:
                    await send_email(
                        to_email=email,
                        subject=f"Clock-In Recorded (ID: {db_record.attendance_id})",
                        body=(
                            f"Dear {first_name},\n\n"
                            f"A clock-in has been recorded for user ID {user.user_id} at {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}.\n"
                            f"Attendance ID: {db_record.attendance_id}\n"
                            f"Location: {db_record.location or 'Not provided'}\n\n"
                            f"Please review in the Employee Management System.\n\n"
                            f"Best regards,\nEmployee Management System"
                        ),
                        request_id=request_id
                    )
            
            # Log action
            system_log = SystemLogs(
                user_id=user.user_id,
                action=SystemAction.CLOCK_IN,
                table_affected="attendance_records",
                record_id=db_record.attendance_id,
                old_values=None,
                new_values=db_record.__dict__,
                ip_address=ip_address,
                user_agent=request.headers.get("user-agent"),
                timestamp=current_time,
                request_id=request_id
            )
            db.add(system_log)
            await db.commit()
            await db.refresh(db_record)
            
        except Exception as db_error:
            await db.rollback()
            # Check for unique constraint violation
            if "unique_user_date" in str(db_error) or "duplicate key value violates unique constraint" in str(db_error):
                raise AttendanceError(detail="User already clocked in for today")
            else:
                logger.error(f"Database error during clock-in for user_id {user.user_id}: {str(db_error)}", extra={"request_id": request_id})
                raise AttendanceError(detail="Error creating attendance record")

        # Invalidate cache
        await invalidate_cache_prefix(f"attendance_history:{user.user_id}")
        invalidate_user_cache(user.user_id)
        logger.info(
            f"Cache invalidated for attendance_history:{user.user_id} and user_id: {user.user_id}",
            extra={"request_id": request_id}
        )

        logger.info(
            f"User clocked in, user_id: {user.user_id}, attendance_id: {db_record.attendance_id}",
            extra={"request_id": request_id, "user_id": user.user_id}
        )
        return AttendanceRecordOut.model_validate(db_record)

    except AttendanceError as e:
        logger.error(f"Attendance error during clock-in for user_id {user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error during clock-in for user_id {user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during clock-in for user_id {user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing clock-in")

async def clock_out(
    request: Request,
    user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.CLOCK_OUT]))
) -> AttendanceRecordOut:
    """Handle employee clock-out with validation, time calculations, and logging."""
    try:
        current_time = datetime.now(timezone.utc)
        current_date = current_time.date()
        eat_tz = ZoneInfo("Africa/Nairobi")  # EAT is UTC+3
        current_time_eat = current_time.astimezone(eat_tz)

        # Find active clock-in record
        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == user.user_id,
            AttendanceRecords.date == current_date,
            AttendanceRecords.clock_out_time.is_(None),
            AttendanceRecords.is_active.is_(True),
            AttendanceRecords.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_record = result.scalar_one_or_none()
        if not db_record:
            raise ResourceNotFoundError(resource="Attendance record", identifier="active clock-in for today")

        # Validate clock-out time
        if db_record.clock_in_time >= current_time:
            raise ValidationError(detail="Clock-out time must be after clock-in time")

        # Get shift pattern details for validation
        query_assignment = select(ShiftAssignments, ShiftPatterns).join(
            ShiftPatterns,
            and_(
                ShiftPatterns.pattern_id == ShiftAssignments.pattern_id,
                ShiftPatterns.is_active.is_(True),
                ShiftPatterns.deleted_at.is_(None)
            )
        ).where(
            ShiftAssignments.user_id == user.user_id,
            ShiftAssignments.effective_from <= current_date,
            or_(
                ShiftAssignments.effective_to >= current_date,
                ShiftAssignments.effective_to.is_(None)
            ),
            ShiftAssignments.is_active.is_(True),
            ShiftAssignments.deleted_at.is_(None)
        )
        result_assignment = await db.execute(query_assignment)
        assignment, shift_pattern = result_assignment.first() or (None, None)

        # Validate minimum shift duration if configured
        if settings.MINIMUM_SHIFT_DURATION and shift_pattern:
            total_hours = calculate_total_hours(
                clock_in=db_record.clock_in_time,
                clock_out=current_time,
                break_duration=db_record.break_duration or shift_pattern.break_duration
            )
            if total_hours is not None and total_hours < settings.MINIMUM_SHIFT_DURATION:
                raise ValidationError(
                    detail=f"Shift duration ({total_hours:.2f} hours) is less than the minimum required ({settings.MINIMUM_SHIFT_DURATION} hours)"
                )

        # Get admin users for notifications BEFORE database operations
        admins = []
        if settings.NOTIFY_ON_ATTENDANCE:
            admins = await get_users_with_permission(Permission.MANAGE_ATTENDANCE, db)

        # Update record
        ip_address = str(request.client.host) if request.client and request.client.host else None
        db_record.clock_out_time = current_time
        db_record.ip_address = ip_address
        total_hours = calculate_total_hours(
            clock_in=db_record.clock_in_time,
            clock_out=db_record.clock_out_time,
            break_duration=db_record.break_duration or (shift_pattern.break_duration if shift_pattern else 0)
        )
        if total_hours is not None:
            db_record.total_hours = total_hours
            if shift_pattern:
                standard_hours = calculate_shift_hours(
                    start_time=shift_pattern.start_time,
                    end_time=shift_pattern.end_time,
                    is_overnight=shift_pattern.is_overnight
                )
            else:
                standard_hours = settings.OVERTIME_THRESHOLD
            
            db_record.overtime_hours = calculate_overtime_hours(
                total_hours,
                standard_hours=standard_hours
            )

        db_record.updated_at = current_time
        db.add(db_record)

        # Send notifications BEFORE commit
        if settings.NOTIFY_ON_ATTENDANCE:
            recipients = [(user.email, user.first_name)]
            recipients.extend([(admin.email, admin.first_name) for admin in admins])
            for email, first_name in recipients:
                await send_email(
                    to_email=email,
                    subject=f"Clock-Out Recorded (ID: {db_record.attendance_id})",
                    body=(
                        f"Dear {first_name},\n\n"
                        f"A clock-out has been recorded for user ID {user.user_id} at {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}.\n"
                        f"Attendance ID: {db_record.attendance_id}\n"
                        f"Total Hours: {db_record.total_hours or 0:.2f}\n"
                        f"Overtime Hours: {db_record.overtime_hours or 0:.2f}\n\n"
                        f"Please review in the Employee Management System.\n\n"
                        f"Best regards,\nEmployee Management System"
                    ),
                    request_id=request_id
                )

        # Log action
        system_log = SystemLogs(
            user_id=user.user_id,
            action=SystemAction.CLOCK_OUT,
            table_affected="attendance_records",
            record_id=db_record.attendance_id,
            old_values=None,
            new_values=db_record.__dict__,
            ip_address=ip_address,
            user_agent=request.headers.get("user-agent"),
            timestamp=current_time,
            request_id=request_id
        )
        db.add(system_log)
        await db.commit()
        await db.refresh(db_record)

        # Invalidate cache
        await invalidate_cache_prefix(f"attendance_history:{user.user_id}")
        invalidate_user_cache(user.user_id)
        logger.info(
            f"Cache invalidated for attendance_history:{user.user_id} and user_id: {user.user_id}",
            extra={"request_id": request_id}
        )

        logger.info(
            f"User clocked out, user_id: {user.user_id}, attendance_id: {db_record.attendance_id}, total_hours: {db_record.total_hours or 0}",
            extra={"request_id": request_id, "user_id": user.user_id}
        )
        return AttendanceRecordOut.model_validate(db_record)

    except ResourceNotFoundError as e:
        logger.error(f"Resource not found during clock-out for user_id {user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error during clock-out for user_id {user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during clock-out for user_id {user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing clock-out")

async def get_attendance_history(
    user_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_OWN_ATTENDANCE, Permission.VIEW_ATTENDANCE]))
) -> List[AttendanceRecordOut]:
    """Retrieve attendance history for a user with date range, pagination, and authorization."""
    try:
        limit = limit or settings.DEFAULT_PAGE_SIZE
        if skip < 0 or limit <= 0:
            raise ValidationError(detail="Invalid pagination parameters")
        if start_date and end_date and start_date > end_date:
            raise ValidationError(detail="Start date must be before or equal to end date")
        if user_id and user_id <= 0:
            raise ValidationError(detail="Invalid user_id")

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if user_id and user_id != current_user.user_id:
            if Permission.VIEW_ATTENDANCE not in user_permissions and Permission.MANAGE_ATTENDANCE not in user_permissions:
                query_supervisor = select(EmployeeHierarchy).where(
                    EmployeeHierarchy.supervisor_id == current_user.user_id,
                    EmployeeHierarchy.employee_id == user_id,
                    EmployeeHierarchy.is_active.is_(True),
                    EmployeeHierarchy.deleted_at.is_(None)
                )
                result_supervisor = await db.execute(query_supervisor)
                if not result_supervisor.scalar_one_or_none():
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized to view this user's attendance history"
                    )

        start_date_str = start_date.isoformat() if start_date else "none"
        end_date_str = end_date.isoformat() if end_date else "none"
        cache_key = f"attendance_history:{user_id or current_user.user_id}:{start_date_str}:{end_date_str}:{skip}:{limit}"

        cached_result = await get_cache(cache_key)
        if cached_result:
            logger.info(f"Cache hit for attendance_history, user_id: {user_id or current_user.user_id}", extra={"request_id": request_id})
            return [AttendanceRecordOut.model_validate(record) for record in cached_result]

        # Validate user_id if provided
        target_user_id = user_id or current_user.user_id
        if user_id:
            query_user = select(Users).where(
                Users.user_id == user_id,
                Users.is_active.is_(True),
                Users.deleted_at.is_(None)
            )
            result_user = await db.execute(query_user)
            if not result_user.scalar_one_or_none():
                raise UserNotFoundError(user_id=user_id)

        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == target_user_id,
            AttendanceRecords.is_active.is_(True),
            AttendanceRecords.deleted_at.is_(None)
        )
        if start_date:
            query = query.where(AttendanceRecords.date >= start_date)
        if end_date:
            query = query.where(AttendanceRecords.date <= end_date)

        query = query.order_by(AttendanceRecords.date.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        records = result.scalars().all()

        records_dict = [AttendanceRecordOut.model_validate(record).model_dump(mode='json') for record in records]
        await set_cache(cache_key, records_dict, ttl=300)
        logger.info(f"Cache set for attendance_history, user_id: {target_user_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(records)} attendance records for user_id: {target_user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [AttendanceRecordOut.model_validate(record) for record in records]

    except ValidationError as e:
        logger.error(f"Validation error in get_attendance_history for user_id {user_id or current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Forbidden access to attendance history for user_id {user_id or current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_attendance_history for user_id {user_id or current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving attendance history")