from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, date
from app.models.attendance_summary import AttendanceSummary
from app.models.users import Users
from app.models.departments import Departments
from app.models.attendance_records import AttendanceRecords
from app.models.system_logs import SystemLogs
from app.schemas.attendance_summary import AttendanceSummaryOut
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import DatabaseError, ResourceNotFoundError, ValidationError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_user_exists, validate_department_exists
import logging

logger = logging.getLogger(__name__)

async def get_attendance_summary_by_user(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_OWN_ATTENDANCE, Permission.VIEW_ALL_ATTENDANCE]))
) -> List[AttendanceSummaryOut]:
    """Retrieve attendance summary for a specific user with optional date range and pagination."""
    try:
        if skip < 0 or limit <= 0:
            raise ValidationError(detail="Invalid pagination parameters")

        cache_key = f"attendance_summary:{user_id}:{start_date or 'none'}:{end_date or 'none'}:{skip}:{limit}"
        cached_result = await get_cache(cache_key)
        if cached_result:
            return [AttendanceSummaryOut(**record) for record in cached_result]

        await validate_user_exists(user_id, db)
        query = (
            select(AttendanceSummary)
            .join(Users, Users.user_id == AttendanceSummary.user_id)
            .join(Departments, Departments.department_id == Users.department_id, isouter=True)
            .where(
                AttendanceSummary.user_id == user_id,
                AttendanceSummary.is_active.is_(True)
            )
        )

        if start_date:
            query = query.where(AttendanceSummary.attendance_summary_date >= start_date)
        if end_date:
            query = query.where(AttendanceSummary.attendance_summary_date <= end_date)

        query = query.offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        result = await db.execute(query)
        summaries = result.scalars().all()

        if not summaries:
            raise ResourceNotFoundError(resource="Attendance summary", identifier=f"user_id {user_id}")

        summaries_dict = [AttendanceSummaryOut.model_validate(summary).model_dump() for summary in summaries]
        await set_cache(cache_key, summaries_dict, ttl=300)

        logger.info(f"Retrieved {len(summaries)} attendance summaries for user_id: {user_id}")
        return [AttendanceSummaryOut.model_validate(summary) for summary in summaries]

    except ResourceNotFoundError:
        raise
    except DatabaseError as e:
        logger.error(f"Database error retrieving attendance summary for user_id {user_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving attendance summary for user_id {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving attendance summary"
        )

async def get_all_attendance_summaries(
    skip: int = 0,
    limit: int = 50,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_ALL_ATTENDANCE]))
) -> List[AttendanceSummaryOut]:
    """Retrieve all attendance summaries with optional date range and pagination."""
    try:
        if skip < 0 or limit <= 0:
            raise ValidationError(detail="Invalid pagination parameters")

        cache_key = f"attendance_summary_all:{start_date or 'none'}:{end_date or 'none'}:{skip}:{limit}"
        cached_result = await get_cache(cache_key)
        if cached_result:
            return [AttendanceSummaryOut(**record) for record in cached_result]

        query = (
            select(AttendanceSummary)
            .join(Users, Users.user_id == AttendanceSummary.user_id)
            .join(Departments, Departments.department_id == Users.department_id, isouter=True)
            .where(AttendanceSummary.is_active.is_(True))
        )

        if start_date:
            query = query.where(AttendanceSummary.attendance_summary_date >= start_date)
        if end_date:
            query = query.where(AttendanceSummary.attendance_summary_date <= end_date)

        query = query.offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        result = await db.execute(query)
        summaries = result.scalars().all()

        summaries_dict = [AttendanceSummaryOut.model_validate(summary).model_dump() for summary in summaries]
        await set_cache(cache_key, summaries_dict, ttl=300)

        logger.info(f"Retrieved {len(summaries)} attendance summaries")
        return [AttendanceSummaryOut.model_validate(summary) for summary in summaries]

    except DatabaseError as e:
        logger.error(f"Database error retrieving all attendance summaries: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving all attendance summaries: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving all attendance summaries"
        )

async def generate_attendance_summary(
    user_id: int,
    attendance_summary_date: date,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.GENERATE_REPORTS]))
) -> AttendanceSummaryOut:
    """Generate an attendance summary for a specific user and date."""
    try:
        if attendance_summary_date > date.today():
            raise ValidationError(detail="Attendance summary date cannot be in the future.")

        await validate_user_exists(user_id, db)
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
            await validate_department_exists(user.department_id, db)
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
        attendance = result.scalar_one_or_none()
        if not attendance:
            raise ResourceNotFoundError(resource="Attendance record", 
                                        identifier=f"user_id {user_id}, date {attendance_summary_date}")

        query = select(AttendanceSummary).where(
            AttendanceSummary.user_id == user_id,
            AttendanceSummary.attendance_summary_date == attendance_summary_date
        )
        result = await db.execute(query)
        db_summary = result.scalar_one_or_none()

        summary_data = {
            "user_id": user_id,
            "employee_id": user.employee_id,
            "full_name": f"{user.first_name} {user.last_name}",
            "department_name": department_name,
            "attendance_summary_date": attendance_summary_date,
            "status": attendance.status,
            "total_hours": float(attendance.total_hours) if attendance.total_hours else None,
            "overtime_hours": float(attendance.overtime_hours) if attendance.overtime_hours else None,
            "clock_in_time": attendance.clock_in_time,
            "clock_out_time": attendance.clock_out_time,
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }

        if db_summary:
            for key, value in summary_data.items():
                if key != "created_at":
                    setattr(db_summary, key, value)
        else:
            db_summary = AttendanceSummary(**summary_data)
            db.add(db_summary)

        await db.commit()
        await db.refresh(db_summary)

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.GENERATE_REPORT,
            table_affected="attendance_summary",
            record_id=db_summary.user_id,
            old_values=None,
            new_values=db_summary.__dict__,
            ip_address=str(request.client.host),
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        await invalidate_cache_prefix(f"attendance_summary:{user_id}")
        await invalidate_cache_prefix(f"attendance_summary_all")
        logger.info(f"Attendance summary generated for user_id: {user_id}, date: {attendance_summary_date}")
        return AttendanceSummaryOut.model_validate(db_summary)

    except ResourceNotFoundError:
        raise
    except DatabaseError as e:
        logger.error(f"Database error generating attendance summary for user_id {user_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error generating attendance summary for user_id {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error generating attendance summary"
        )