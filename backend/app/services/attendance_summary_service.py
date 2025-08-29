from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
from app.models.attendance_summary import AttendanceSummary
from app.models.users import Users
from app.models.departments import Departments
from app.models.attendance_records import AttendanceRecords
from app.models.employee_hierarchy import EmployeeHierarchy
from app.schemas.attendance_summary import AttendanceSummaryOut
from app.schemas.system_log import SystemLogCreate
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.security import get_current_user
from app.core.permissions import require_permissions_dependency, invalidate_user_cache, get_user_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_user_exists, validate_department_exists
from app.core.utils import get_request_id, get_users_with_permission, serialize_dict_for_logging, serialize_model_for_logging
from app.services.system_log_service import create_system_log
from app.core.mail import send_email
import logging

logger = logging.getLogger(__name__)

async def _check_user_authorization(
    db: AsyncSession,
    current_user: Users,
    target_user_id: int,
    required_permissions: List[Permission],
    request_id: Optional[str] = None
) -> bool:
    """Check if the current user is authorized to perform actions on the target user's attendance summaries."""
    user_permissions = await get_user_permissions(current_user.user_id, db)
    if target_user_id == current_user.user_id and Permission.VIEW_OWN_ATTENDANCE.value in user_permissions:
        return True
    if any(p.value in user_permissions for p in required_permissions):
        return True
    query_hierarchy = select(EmployeeHierarchy).where(
        EmployeeHierarchy.employee_id == target_user_id,
        EmployeeHierarchy.supervisor_id == current_user.user_id,
        EmployeeHierarchy.is_active.is_(True),
        EmployeeHierarchy.deleted_at.is_(None)
    )
    result_hierarchy = await db.execute(query_hierarchy)
    return bool(result_hierarchy.scalar_one_or_none())

async def get_attendance_summary_by_user(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    department_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_OWN_ATTENDANCE, Permission.VIEW_ALL_ATTENDANCE]))
) -> List[AttendanceSummaryOut]:
    """Retrieve attendance summary for a specific user with optional filters and pagination."""
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user ID")
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")
        if start_date and end_date and start_date > end_date:
            raise ValidationError(detail="start_date cannot be later than end_date")
        if user_id and department_id:
            raise ValidationError(detail="Cannot specify both user_id and department_id")

        # Authorization check
        if not await _check_user_authorization(db, current_user, user_id, [Permission.VIEW_ALL_ATTENDANCE, Permission.MANAGE_EMPLOYEES], request_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this user's attendance summary"
            )

        cache_key = f"attendance_summary:{user_id or 'all'}:{department_id or 'all'}:{start_date or 'none'}:{end_date or 'none'}:{is_active or 'all'}:{skip}:{limit or settings.DEFAULT_PAGE_SIZE}"
        cached_result = await get_cache(cache_key)
        if cached_result:
            logger.info(f"Cache hit for {cache_key}", extra={"request_id": request_id})
            return [AttendanceSummaryOut(**record) for record in cached_result]

        await validate_user_exists(db, user_id, request_id)
        query = (
            select(AttendanceSummary)
            .join(Users, Users.user_id == AttendanceSummary.user_id)
            .join(Departments, Departments.department_id == Users.department_id, isouter=True)
        )

        if is_active is not None:
            query = query.where(AttendanceSummary.is_active.is_(is_active))
        else:
            query = query.where(AttendanceSummary.is_active.is_(True))

        if user_id:
            query = query.where(AttendanceSummary.user_id == user_id)
        if department_id:
            await validate_department_exists(db, department_id, request_id)
            query = query.where(Users.department_id == department_id)
        if start_date:
            query = query.where(AttendanceSummary.attendance_summary_date >= start_date)
        if end_date:
            query = query.where(AttendanceSummary.attendance_summary_date <= end_date)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = query.order_by(AttendanceSummary.attendance_summary_date.asc()).offset(skip).limit(limit)
        result = await db.execute(query)
        summaries = result.scalars().all()

        if not summaries:
            raise ResourceNotFoundError(resource="Attendance summary", identifier=f"user_id {user_id}")

        summaries_dict = [AttendanceSummaryOut.model_validate(summary).model_dump() for summary in summaries]
        await set_cache(cache_key, summaries_dict, ttl=300)
        logger.info(f"Cache set for {cache_key}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(summaries)} attendance summaries for user_id: {user_id}, department_id: {department_id or 'all'}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [AttendanceSummaryOut.model_validate(summary) for summary in summaries]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ResourceNotFoundError as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error retrieving attendance summary for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving attendance summary for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving attendance summary")

async def get_all_attendance_summaries(
    department_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_ALL_ATTENDANCE]))
) -> List[AttendanceSummaryOut]:
    """Retrieve all attendance summaries with optional filters and pagination."""
    try:
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")
        if start_date and end_date and start_date > end_date:
            raise ValidationError(detail="start_date cannot be later than end_date")

        cache_key = f"attendance_summary_all:{department_id or 'all'}:{start_date or 'none'}:{end_date or 'none'}:{is_active or 'all'}:{skip}:{limit or settings.DEFAULT_PAGE_SIZE}"
        cached_result = await get_cache(cache_key)
        if cached_result:
            logger.info(f"Cache hit for {cache_key}", extra={"request_id": request_id})
            return [AttendanceSummaryOut(**record) for record in cached_result]

        query = (
            select(AttendanceSummary)
            .join(Users, Users.user_id == AttendanceSummary.user_id)
            .join(Departments, Departments.department_id == Users.department_id, isouter=True)
        )

        if is_active is not None:
            query = query.where(AttendanceSummary.is_active.is_(is_active))
        else:
            query = query.where(AttendanceSummary.is_active.is_(True))

        if department_id:
            await validate_department_exists(db, department_id, request_id)
            query = query.where(Users.department_id == department_id)
        if start_date:
            query = query.where(AttendanceSummary.attendance_summary_date >= start_date)
        if end_date:
            query = query.where(AttendanceSummary.attendance_summary_date <= end_date)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = query.order_by(AttendanceSummary.attendance_summary_date.asc()).offset(skip).limit(limit)
        result = await db.execute(query)
        summaries = result.scalars().all()

        summaries_dict = [AttendanceSummaryOut.model_validate(summary).model_dump() for summary in summaries]
        await set_cache(cache_key, summaries_dict, ttl=300)
        logger.info(f"Cache set for {cache_key}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(summaries)} attendance summaries, department_id: {department_id or 'all'}",
            extra={"request_id": request_id}
        )
        return [AttendanceSummaryOut.model_validate(summary) for summary in summaries]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ResourceNotFoundError as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving all attendance summaries: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving all attendance summaries")

async def generate_attendance_summary(
    user_id: int,
    attendance_summary_date: date,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.GENERATE_REPORTS]))
) -> AttendanceSummaryOut:
    """Generate or update an attendance summary for a specific user and date."""
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user ID")
        if attendance_summary_date > date.today():
            raise ValidationError(detail="Attendance summary date cannot be in the future")

        # Authorization check
        if not await _check_user_authorization(db, current_user, user_id, [Permission.GENERATE_REPORTS, Permission.MANAGE_EMPLOYEES], request_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to generate attendance summary for this user"
            )

        await validate_user_exists(db, user_id, request_id)
        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            raise ResourceNotFoundError(resource="User", identifier=f"user_id {user_id}")

        department_name = None
        if user.department_id:
            await validate_department_exists(db, user.department_id, request_id)
            query = select(Departments).where(
                Departments.department_id == user.department_id,
                Departments.is_active.is_(True),
                Departments.deleted_at.is_(None)
            )
            result = await db.execute(query)
            department = result.scalar_one_or_none()
            department_name = department.department_name if department else None

        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == user_id,
            AttendanceRecords.date == attendance_summary_date,
            AttendanceRecords.is_active.is_(True)
        )
        result = await db.execute(query)
        attendance = result.scalars().first()
        if not attendance:
            raise ResourceNotFoundError(resource="Attendance record", 
                                        identifier=f"user_id {user_id}, date {attendance_summary_date}")

        query = select(AttendanceSummary).where(
            AttendanceSummary.user_id == user_id,
            AttendanceSummary.attendance_summary_date == attendance_summary_date,
            AttendanceSummary.is_active.is_(True)
        )
        result = await db.execute(query)
        db_summary = result.scalars().first()

        # Compute total_hours and overtime_hours
        total_hours = float(attendance.total_hours) if attendance.total_hours else 0.0
        overtime_hours = float(attendance.overtime_hours) if attendance.overtime_hours else 0.0

        summary_data = {
            "user_id": user_id,
            "employee_id": user.employee_id,
            "full_name": f"{user.first_name} {user.last_name}",
            "department_name": department_name,
            "attendance_summary_date": attendance_summary_date,
            "status": attendance.status,
            "total_hours": total_hours,
            "overtime_hours": overtime_hours,
            "clock_in_time": attendance.clock_in_time,
            "clock_out_time": attendance.clock_out_time,
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }

        old_values = None
        if db_summary:
            old_values = db_summary.__dict__.copy()
            for key, value in summary_data.items():
                if key != "created_at":
                    setattr(db_summary, key, value)
        else:
            db_summary = AttendanceSummary(**summary_data)
            db.add(db_summary)

        await db.commit()
        await db.refresh(db_summary)

        # Log the action using the helper functions for serialization
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.GENERATE_REPORT,
            table_affected="attendance_summary",
            record_id=db_summary.user_id,
            old_values=serialize_dict_for_logging(old_values),
            new_values=serialize_model_for_logging(db_summary),
            ip_address=str(request.client.host),
            user_agent=request.headers.get("user-agent"),
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, settings, request_id)

        # Invalidate cache
        invalidate_user_cache(user_id)
        await invalidate_cache_prefix(f"attendance_summary:{user_id}")
        await invalidate_cache_prefix("attendance_summary_all")
        logger.info(f"Cache invalidated for attendance_summary:{user_id} and attendance_summary_all", extra={"request_id": request_id})

        # Notify admins
        await _notify_admins_of_summary_generation(db, db_summary, current_user, request_id, settings)

        logger.info(
            f"Attendance summary generated for user_id: {user_id}, date: {attendance_summary_date}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return AttendanceSummaryOut.model_validate(db_summary)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ResourceNotFoundError as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error generating attendance summary for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error generating attendance summary for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error generating attendance summary")

async def _notify_admins_of_summary_generation(
    db: AsyncSession,
    summary: AttendanceSummary,
    current_user: Users,
    request_id: Optional[str],
    settings: Settings
) -> None:
    """Send notification email to admins about attendance summary generation."""
    try:
        eat_tz = ZoneInfo("Africa/Nairobi")
        current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
        admins = await get_users_with_permission(Permission.MANAGE_EMPLOYEES, db)
        recipients = [(admin.email, admin.first_name) for admin in admins if admin.email]

        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"Attendance Summary Generated for {summary.full_name} (ID: {summary.user_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"An attendance summary has been generated by {current_user.first_name} {current_user.last_name} ({current_user.email}).\n\n"
                    f"Details:\n"
                    f"User ID: {summary.user_id}\n"
                    f"Employee ID: {summary.employee_id}\n"
                    f"Full Name: {summary.full_name}\n"
                    f"Department: {summary.department_name or 'N/A'}\n"
                    f"Date: {summary.attendance_summary_date}\n"
                    f"Status: {summary.status}\n"
                    f"Total Hours: {summary.total_hours or 'N/A'}\n"
                    f"Overtime Hours: {summary.overtime_hours or 'N/A'}\n"
                    f"Clock In: {summary.clock_in_time or 'N/A'}\n"
                    f"Clock Out: {summary.clock_out_time or 'N/A'}\n"
                    f"Generated At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )
        logger.info(
            f"Sent notifications to {len(recipients)} admins for attendance summary generation, user_id={summary.user_id}",
            extra={"request_id": request_id}
        )
    except Exception as e:
        logger.error(
            f"Failed to send notifications for attendance summary generation, user_id={summary.user_id}: {str(e)}",
            extra={"request_id": request_id}
        )