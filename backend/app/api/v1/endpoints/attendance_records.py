from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone, date
from app.core.database import AsyncSessionLocal
from app.models.attendance_records import AttendanceRecords
from app.models.time_corrections import TimeCorrections
from app.models.overtime_records import OvertimeRecords
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.core.security import check_user_permission
from app.core.config import settings
import logging
from fastapi.responses import FileResponse
import csv
import io
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attendance-records", tags=["Attendance Records"])

class ClockInOut(BaseModel):
    """Schema for clock-in/out requests."""
    action: str  # 'clock_in' or 'clock_out'

    model_config = ConfigDict(from_attributes=True)

class AttendanceRecordOut(BaseModel):
    """Schema for attendance record output."""
    record_id: int
    user_id: int
    clock_in_time: datetime
    clock_out_time: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

class TimeCorrectionCreate(BaseModel):
    """Schema for creating a time correction request."""
    record_id: int
    corrected_clock_in: Optional[datetime]
    corrected_clock_out: Optional[datetime]
    reason: str

    model_config = ConfigDict(from_attributes=True)

class TimeCorrectionOut(BaseModel):
    """Schema for time correction output."""
    correction_id: int
    record_id: int
    user_id: int
    corrected_clock_in: Optional[datetime]
    corrected_clock_out: Optional[datetime]
    reason: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class AttendanceSummary(BaseModel):
    """Schema for attendance summary output."""
    user_id: int
    total_hours: float
    overtime_hours: float
    period_start: date
    period_end: date

    model_config = ConfigDict(from_attributes=True)

async def get_db() -> AsyncSession:
    """Dependency to provide an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {str(e)}")
            await session.rollback()
            raise
        finally:
            await session.close()

async def get_current_active_user(db: AsyncSession = Depends(get_db)) -> Users:
    """Dependency to get the current active user."""
    query = select(Users).where(Users.is_active == True, Users.deleted_at == None)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")
    return user

async def is_manager_or_hr_or_admin(db: AsyncSession, user: Users) -> bool:
    """
    Check if the user has Manager, HR, Admin, or Super_Admin role.

    Args:
        db: Async database session.
        user: Current user object.

    Returns:
        bool: True if user has required role, False otherwise.
    """
    try:
        query = select(UserRoles).join(Roles).where(
            UserRoles.user_id == user.user_id,
            UserRoles.is_active == True,
            Roles.role_name.in_(["Manager", "HR", "Admin", "Super_Admin"]),
            Roles.is_active == True
        )
        result = await db.execute(query)
        return result.scalar_one_or_none() is not None
    except Exception as e:
        logger.error(f"Error checking role for user_id {user.user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error checking user role")

@router.post("/clock", response_model=AttendanceRecordOut, status_code=status.HTTP_201_CREATED, summary="Clock in or out", description="Record clock-in or clock-out for an employee.")
async def clock_in_out(
    clock_data: ClockInOut,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> AttendanceRecordOut:
    """
    Record a clock-in or clock-out action for the current user.

    Args:
        clock_data: Clock-in or clock-out action.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        AttendanceRecordOut: Created or updated attendance record.

    Raises:
        HTTPException: If action is invalid or record conflicts exist.
    """
    try:
        if clock_data.action not in ["clock_in", "clock_out"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action")

        if clock_data.action == "clock_in":
            query = select(AttendanceRecords).where(
                AttendanceRecords.user_id == current_user.user_id,
                AttendanceRecords.clock_out_time == None,
                AttendanceRecords.is_active == True
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active clock-in already exists")

            record = AttendanceRecords(
                user_id=current_user.user_id,
                clock_in_time=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_active=True
            )
            db.add(record)

        else:  # clock_out
            query = select(AttendanceRecords).where(
                AttendanceRecords.user_id == current_user.user_id,
                AttendanceRecords.clock_out_time == None,
                AttendanceRecords.is_active == True
            )
            result = await db.execute(query)
            record = result.scalar_one_or_none()
            if not record:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active clock-in found")

            record.clock_out_time = datetime.now(timezone.utc)
            record.updated_at = datetime.now(timezone.utc)
            db.add(record)

        await db.commit()
        await db.refresh(record)

        logger.info(f"Clock {clock_data.action} recorded for user_id: {current_user.user_id}, record_id: {record.record_id}")
        return AttendanceRecordOut.model_validate(record)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording clock {clock_data.action} for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing clock action")

@router.get("/history", response_model=List[AttendanceRecordOut], summary="Get attendance history", description="Retrieve attendance history for the current user with pagination.")
async def get_attendance_history(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[AttendanceRecordOut]:
    """
    Get paginated attendance history for the current user.

    Args:
        skip: Number of records to skip.
        limit: Maximum number of records to return.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        List[AttendanceRecordOut]: List of attendance records.

    Raises:
        HTTPException: If an error occurs.
    """
    try:
        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == current_user.user_id,
            AttendanceRecords.is_active == True
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        records = result.scalars().all()

        logger.info(f"Retrieved {len(records)} attendance records for user_id: {current_user.user_id}")
        return [AttendanceRecordOut.model_validate(record) for record in records]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving attendance history for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving attendance history")

@router.post("/time-correction", response_model=TimeCorrectionOut, status_code=status.HTTP_201_CREATED, summary="Request time correction", description="Submit a time correction request for an attendance record.")
async def request_time_correction(
    correction: TimeCorrectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> TimeCorrectionOut:
    """
    Submit a time correction request for an attendance record.

    Args:
        correction: Time correction request data.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        TimeCorrectionOut: Created time correction request.

    Raises:
        HTTPException: If record not found or invalid data.
    """
    try:
        query = select(AttendanceRecords).where(
            AttendanceRecords.record_id == correction.record_id,
            AttendanceRecords.user_id == current_user.user_id,
            AttendanceRecords.is_active == True
        )
        result = await db.execute(query)
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance record not found")

        db_correction = TimeCorrections(
            record_id=correction.record_id,
            user_id=current_user.user_id,
            corrected_clock_in=correction.corrected_clock_in,
            corrected_clock_out=correction.corrected_clock_out,
            reason=correction.reason,
            status="pending",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_correction)
        await db.commit()
        await db.refresh(db_correction)

        logger.info(f"Time correction requested for record_id: {correction.record_id}, user_id: {current_user.user_id}")
        return TimeCorrectionOut.model_validate(db_correction)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error requesting time correction for record_id {correction.record_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error requesting time correction")

@router.get("/time-corrections", response_model=List[TimeCorrectionOut], summary="Get time correction requests", description="Retrieve time correction requests for a user or team (manager/HR/admin).")
async def get_time_corrections(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[TimeCorrectionOut]:
    """
    Get paginated time correction requests for a user or team.

    Args:
        user_id: Optional user ID to filter corrections (manager/HR/admin only).
        skip: Number of records to skip.
        limit: Maximum number of records to return.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        List[TimeCorrectionOut]: List of time correction requests.

    Raises:
        HTTPException: If user lacks permission or an error occurs.
    """
    try:
        if user_id and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view others' corrections")

        query = select(TimeCorrections)
        if user_id:
            query = query.where(TimeCorrections.user_id == user_id)
        else:
            query = query.where(TimeCorrections.user_id == current_user.user_id)
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        corrections = result.scalars().all()

        logger.info(f"Retrieved {len(corrections)} time corrections for user_id: {user_id or current_user.user_id}")
        return [TimeCorrectionOut.model_validate(correction) for correction in corrections]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving time corrections: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving time corrections")

@router.put("/time-corrections/{correction_id}", response_model=TimeCorrectionOut, summary="Approve/reject time correction", description="Approve or reject a time correction request. Requires approve_time_corrections permission or manager/HR/admin access.")
async def approve_reject_time_correction(
    correction_id: int,
    status_update: str,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> TimeCorrectionOut:
    """
    Approve or reject a time correction request.

    Args:
        correction_id: ID of the time correction request.
        status_update: New status ('approved' or 'rejected').
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        TimeCorrectionOut: Updated time correction request.

    Raises:
        HTTPException: If user lacks permission, correction not found, or invalid status.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "approve_time_corrections")
        if not has_permission and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to approve/reject corrections")

        if status_update not in ["approved", "rejected"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")

        query = select(TimeCorrections).where(TimeCorrections.correction_id == correction_id)
        result = await db.execute(query)
        correction = result.scalar_one_or_none()
        if not correction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time correction not found")

        correction.status = status_update
        correction.updated_at = datetime.now(timezone.utc)

        if status_update == "approved":
            query = select(AttendanceRecords).where(AttendanceRecords.record_id == correction.record_id)
            result = await db.execute(query)
            record = result.scalar_one_or_none()
            if not record:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance record not found")

            if correction.corrected_clock_in:
                record.clock_in_time = correction.corrected_clock_in
            if correction.corrected_clock_out:
                record.clock_out_time = correction.corrected_clock_out
            record.updated_at = datetime.now(timezone.utc)
            db.add(record)

        db.add(correction)
        await db.commit()
        await db.refresh(correction)

        logger.info(f"Time correction {correction_id} {status_update} by user_id: {current_user.user_id}")
        return TimeCorrectionOut.model_validate(correction)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing time correction {correction_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing time correction")

@router.get("/summary", response_model=AttendanceSummary, summary="Get attendance summary", description="Get monthly attendance summary for a user or team (manager/HR/admin).")
async def get_attendance_summary(
    user_id: Optional[int] = None,
    start_date: date = date.today().replace(day=1),
    end_date: date = date.today(),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> AttendanceSummary:
    """
    Get attendance summary for a user or team for a specified period.

    Args:
        user_id: Optional user ID to filter summary (manager/HR/admin only).
        start_date: Start date of the period.
        end_date: End date of the period.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        AttendanceSummary: Summary of total and overtime hours.

    Raises:
        HTTPException: If user lacks permission or an error occurs.
    """
    try:
        if user_id and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view others' summaries")

        target_user_id = user_id or current_user.user_id

        query = select(
            func.sum(func.extract('epoch', AttendanceRecords.clock_out_time - AttendanceRecords.clock_in_time) / 3600)
        ).where(
            AttendanceRecords.user_id == target_user_id,
            AttendanceRecords.clock_out_time != None,
            AttendanceRecords.clock_in_time >= start_date,
            AttendanceRecords.clock_out_time <= end_date,
            AttendanceRecords.is_active == True
        )
        result = await db.execute(query)
        total_hours = result.scalar() or 0.0

        query = select(
            func.sum(func.extract('epoch', OvertimeRecords.duration) / 3600)
        ).where(
            OvertimeRecords.user_id == target_user_id,
            OvertimeRecords.start_time >= start_date,
            OvertimeRecords.end_time <= end_date,
            OvertimeRecords.is_active == True
        )
        result = await db.execute(query)
        overtime_hours = result.scalar() or 0.0

        logger.info(f"Attendance summary retrieved for user_id: {target_user_id}")
        return AttendanceSummary(
            user_id=target_user_id,
            total_hours=total_hours,
            overtime_hours=overtime_hours,
            period_start=start_date,
            period_end=end_date
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving attendance summary for user_id {target_user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving attendance summary")

@router.get("/export/csv", response_model=None, summary="Export attendance history as CSV", description="Export attendance history as a CSV file.")
async def export_attendance_csv(
    start_date: date = date.today().replace(day=1),
    end_date: date = date.today(),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> FileResponse:
    """
    Export attendance history as a CSV file.

    Args:
        start_date: Start date of the period.
        end_date: End date of the period.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        FileResponse: CSV file with attendance history.

    Raises:
        HTTPException: If an error occurs.
    """
    try:
        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == current_user.user_id,
            AttendanceRecords.clock_in_time >= start_date,
            AttendanceRecords.clock_out_time <= end_date,
            AttendanceRecords.is_active == True
        )
        result = await db.execute(query)
        records = result.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Record ID", "Clock In", "Clock Out", "Created At", "Updated At"])
        for record in records:
            writer.writerow([
                record.record_id,
                record.clock_in_time,
                record.clock_out_time,
                record.created_at,
                record.updated_at
            ])

        output.seek(0)
        filename = f"attendance_{current_user.user_id}_{start_date}_to_{end_date}.csv"
        with open(filename, "w") as f:
            f.write(output.getvalue())

        logger.info(f"Attendance CSV exported for user_id: {current_user.user_id}")
        return FileResponse(filename, media_type="text/csv", filename=filename)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting attendance CSV for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error exporting attendance CSV")
    finally:
        if os.path.exists(filename):
            os.remove(filename)

@router.get("/export/pdf", response_model=None, summary="Export attendance history as PDF", description="Export attendance history as a PDF file.")
async def export_attendance_pdf(
    start_date: date = date.today().replace(day=1),
    end_date: date = date.today(),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> FileResponse:
    """
    Export attendance history as a PDF file.

    Args:
        start_date: Start date of the period.
        end_date: End date of the period.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        FileResponse: PDF file with attendance history.

    Raises:
        HTTPException: If an error occurs.
    """
    try:
        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == current_user.user_id,
            AttendanceRecords.clock_in_time >= start_date,
            AttendanceRecords.clock_out_time <= end_date,
            AttendanceRecords.is_active == True
        )
        result = await db.execute(query)
        records = result.scalars().all()

        filename = f"attendance_{current_user.user_id}_{start_date}_to_{end_date}.pdf"
        doc = SimpleDocTemplate(filename, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        data = [["Record ID", "Clock In", "Clock Out", "Created At", "Updated At"]]
        for record in records:
            data.append([
                str(record.record_id),
                str(record.clock_in_time),
                str(record.clock_out_time) if record.clock_out_time else "",
                str(record.created_at),
                str(record.updated_at)
            ])

        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(table)

        doc.build(elements)

        logger.info(f"Attendance PDF exported for user_id: {current_user.user_id}")
        return FileResponse(filename, media_type="application/pdf", filename=filename)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting attendance PDF for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error exporting attendance PDF")
    finally:
        if os.path.exists(filename):
            os.remove(filename)