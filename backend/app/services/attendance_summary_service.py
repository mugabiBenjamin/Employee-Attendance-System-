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
from app.core.exceptions import DatabaseError, ResourceNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db
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
    """
    Retrieve attendance summary for a specific user with optional date range and pagination.
    Requires VIEW_OWN_ATTENDANCE or VIEW_ALL_ATTENDANCE permission.
    """
    try:
        if skip < 0 or limit <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid pagination parameters"
            )

        query = (
            select(AttendanceSummary)
            .join(Users, Users.user_id == AttendanceSummary.user_id)
            .join(Departments, Departments.department_id == Users.department_id, isouter=True)
            .where(
                AttendanceSummary.user_id == user_id,
                AttendanceSummary.is_active == True
            )
        )

        if start_date:
            query = query.where(AttendanceSummary.date >= start_date)
        if end_date:
            query = query.where(AttendanceSummary.date <= end_date)

        query = query.offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        result = await db.execute(query)
        summaries = result.scalars().all()

        if not summaries:
            raise ResourceNotFoundError(resource="Attendance summary", identifier=f"user_id {user_id}")

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
    """
    Retrieve all attendance summaries with optional date range and pagination.
    Requires VIEW_ALL_ATTENDANCE permission.
    """
    try:
        if skip < 0 or limit <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid pagination parameters"
            )

        query = (
            select(AttendanceSummary)
            .join(Users, Users.user_id == AttendanceSummary.user_id)
            .join(Departments, Departments.department_id == Users.department_id, isouter=True)
            .where(AttendanceSummary.is_active == True)
        )

        if start_date:
            query = query.where(AttendanceSummary.date >= start_date)
        if end_date:
            query = query.where(AttendanceSummary.date <= end_date)

        query = query.offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        result = await db.execute(query)
        summaries = result.scalars().all()

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
    date: date,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.GENERATE_REPORTS]))
) -> AttendanceSummaryOut:
    """
    Generate an attendance summary for a specific user and date.
    Requires GENERATE_REPORTS permission.
    """
    try:
        # Validate user
        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            raise ResourceNotFoundError(resource="User", identifier=f"user_id {user_id}")

        # Get department
        department_name = None
        if user.department_id:
            query = select(Departments).where(
                Departments.department_id == user.department_id,
                Departments.is_active == True,
                Departments.deleted_at == None
            )
            result = await db.execute(query)
            department = result.scalar_one_or_none()
            department_name = department.department_name if department else None

        # Get attendance record
        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == user_id,
            AttendanceRecords.date == date,
            AttendanceRecords.is_active == True
        )
        result = await db.execute(query)
        attendance = result.scalar_one_or_none()

        if not attendance:
            raise ResourceNotFoundError(resource="Attendance record", identifier=f"user_id {user_id}, date {date}")

        # Create or update summary
        query = select(AttendanceSummary).where(
            AttendanceSummary.user_id == user_id,
            AttendanceSummary.date == date
        )
        result = await db.execute(query)
        db_summary = result.scalar_one_or_none()

        summary_data = {
            "user_id": user_id,
            "employee_id": user.employee_id,
            "full_name": f"{user.first_name} {user.last_name}",
            "department_name": department_name,
            "date": date,
            "status": attendance.status,
            "total_hours": str(attendance.total_hours) if attendance.total_hours else None,
            "overtime_hours": str(attendance.overtime_hours) if attendance.overtime_hours else None,
            "clock_in_time": attendance.clock_in_time,
            "clock_out_time": attendance.clock_out_time,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }

        if db_summary:
            for key, value in summary_data.items():
                if key not in ("created_at",):
                    setattr(db_summary, key, value)
        else:
            db_summary = AttendanceSummary(**summary_data)
            db.add(db_summary)

        await db.commit()
        await db.refresh(db_summary)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.VIEW_REPORT,
            table_affected="attendance_summary",
            record_id=user_id,
            old_values=None,
            new_values=db_summary.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Attendance summary generated for user_id: {user_id}, date: {date}")
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