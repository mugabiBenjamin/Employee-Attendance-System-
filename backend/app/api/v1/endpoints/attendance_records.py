from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional
from datetime import datetime, timezone, date
from app.core.database import get_db, invalidate_cache_prefix
from app.models.attendance_records import AttendanceRecords
from app.models.time_corrections import TimeCorrections
from app.models.users import Users
from app.core.permissions import (
    check_permissions, 
    require_permissions,
    require_employee_permissions
)
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission, CorrectionStatus, AttendanceStatus
from app.schemas.attendance_record import AttendanceRecordOut
from app.schemas.time_correction import TimeCorrectionApproval, TimeCorrectionCreate, TimeCorrectionOut
from app.schemas.attendance_summary import AttendanceSummaryOut
from app.core.exceptions import FileUploadError, ValidationError, DatabaseError, ResourceNotFoundError, AttendanceError
import logging
import csv
import io
import aiofiles
import asyncio
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/attendance-records", tags=["Attendance Records"])

class ClockInOut(BaseModel):
    action: str  # 'clock_in' or 'clock_out'
    model_config = ConfigDict(from_attributes=True)

async def _delete_file(filename: str):
    """Background task to delete file after response."""
    try:
        async with aiofiles.os.stat(filename) as _:
            await aiofiles.os.remove(filename)
            logger.info(f"File deleted: {filename}")
    except FileNotFoundError:
        logger.warning(f"File not found for deletion: {filename}")
    except OSError as e:
        logger.error(f"Error deleting file {filename}: {str(e)}")

async def _generate_pdf(data: List[List[str]], filename: str):
    """Generate PDF in an executor to avoid blocking."""
    try:
        loop = asyncio.get_event_loop()
        def build_pdf():
            doc = SimpleDocTemplate(filename, pagesize=letter)
            table = Table(data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            doc.build([table])
        await loop.run_in_executor(None, build_pdf)
    except ValueError as e:
        logger.error(f"Invalid data for PDF generation: {str(e)}")
        raise ValidationError(detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in PDF generation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error generating PDF"
        )

@router.post("/clock", 
            response_model=AttendanceRecordOut, 
            status_code=status.HTTP_201_CREATED,
            dependencies=[Depends(require_employee_permissions())],
            summary="Clock in or out", 
            description="Record clock-in or clock-out for an employee.")
@limiter.limit("5/minute")
async def clock_in_out(
    request: Request,
    clock_data: ClockInOut,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> AttendanceRecordOut:
    try:
        if clock_data.action not in ["clock_in", "clock_out"]:
            raise ValidationError(detail="Invalid action. Must be 'clock_in' or 'clock_out'")

        if clock_data.action == "clock_in":
            query = select(AttendanceRecords).where(
                AttendanceRecords.user_id == current_user.user_id,
                AttendanceRecords.clock_out_time == None,
                AttendanceRecords.is_active == True
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise AttendanceError(detail="You are already clocked in")

            record = AttendanceRecords(
                user_id=current_user.user_id,
                clock_in_time=datetime.now(timezone.utc),
                date=date.today(),
                status=AttendanceStatus.PRESENT,
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
                raise ResourceNotFoundError(resource="Attendance record", identifier="active clock-in")

            clock_out_time = datetime.now(timezone.utc)
            if clock_out_time <= record.clock_in_time:
                raise ValidationError(detail="clock_out_time must be after clock_in_time")
            record.clock_out_time = clock_out_time
            record.updated_at = datetime.now(timezone.utc)
            db.add(record)

        await db.commit()
        await db.refresh(record)

        # Invalidate cache for attendance history
        await invalidate_cache_prefix(f"attendance_history:{current_user.user_id}")

        logger.info(f"Clock {clock_data.action} recorded for user_id: {current_user.user_id}")
        return AttendanceRecordOut.model_validate(record)

    except ValidationError as e:
        logger.error(f"Validation error in clock_in_out for user_id {current_user.user_id}: {str(e)}")
        raise
    except AttendanceError as e:
        logger.error(f"Attendance error in clock_in_out for user_id {current_user.user_id}: {str(e)}")
        raise
    except ResourceNotFoundError as e:
        logger.error(f"Resource not found in clock_in_out for user_id {current_user.user_id}: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in clock_in_out for user_id {current_user.user_id}: {str(e)}")
        raise DatabaseError(message="Database error processing clock action", original_error=e)
    except Exception as e:
        logger.error(f"Unexpected error in clock_in_out for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error processing clock action"
        )

@router.get("/history", 
            response_model=List[AttendanceRecordOut],
            dependencies=[Depends(require_permissions([Permission.VIEW_OWN_ATTENDANCE]))],
            summary="Get attendance history", 
            description="Retrieve attendance history for the current user with pagination.")
async def get_attendance_history(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> List[AttendanceRecordOut]:
    try:
        if skip < 0 or limit <= 0:
            raise ValidationError(detail="Invalid pagination parameters")

        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == current_user.user_id,
            AttendanceRecords.is_active == True
        ).order_by(AttendanceRecords.created_at.desc()).offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        
        result = await db.execute(query)
        records = result.scalars().all()

        logger.info(f"Retrieved {len(records)} attendance records for user_id: {current_user.user_id}")
        return [AttendanceRecordOut.model_validate(record) for record in records]

    except ValidationError as e:
        logger.error(f"Validation error in get_attendance_history for user_id {current_user.user_id}: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_attendance_history for user_id {current_user.user_id}: {str(e)}")
        raise DatabaseError(message="Database error retrieving attendance history", original_error=e)
    except Exception as e:
        logger.error(f"Unexpected error in get_attendance_history for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error retrieving attendance history"
        )

@router.post("/time-correction", 
            response_model=TimeCorrectionOut, 
            status_code=status.HTTP_201_CREATED,
            dependencies=[Depends(require_permissions([Permission.VIEW_OWN_ATTENDANCE]))],
            summary="Request time correction", 
            description="Submit a time correction request for an attendance record.")
async def request_time_correction(
    correction: TimeCorrectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> TimeCorrectionOut:
    try:
        query = select(AttendanceRecords).where(
            AttendanceRecords.attendance_id == correction.attendance_id,
            AttendanceRecords.user_id == current_user.user_id,
            AttendanceRecords.is_active == True
        )
        result = await db.execute(query)
        record = result.scalar_one_or_none()
        if not record:
            raise ResourceNotFoundError(resource="Attendance record", identifier=str(correction.attendance_id))

        db_correction = TimeCorrections(
            attendance_id=correction.attendance_id,
            user_id=current_user.user_id,
            corrected_clock_in=correction.corrected_clock_in,
            corrected_clock_out=correction.corrected_clock_out,
            reason=correction.reason,
            status=CorrectionStatus.UNDER_REVIEW,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_correction)
        await db.commit()
        await db.refresh(db_correction)

        # Invalidate cache for attendance history
        await invalidate_cache_prefix(f"attendance_history:{current_user.user_id}")

        logger.info(f"Time correction requested for attendance_id: {correction.attendance_id}")
        return TimeCorrectionOut.model_validate(db_correction)

    except ResourceNotFoundError as e:
        logger.error(f"Resource not found in request_time_correction for user_id {current_user.user_id}: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in request_time_correction for user_id {current_user.user_id}: {str(e)}")
        raise DatabaseError(message="Database error requesting time correction", original_error=e)
    except Exception as e:
        logger.error(f"Unexpected error in request_time_correction for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error requesting time correction"
        )

@router.get("/time-corrections", 
            response_model=List[TimeCorrectionOut],
            summary="Get time correction requests", 
            description="Retrieve time correction requests for current user or team (if authorized).")
async def get_time_corrections(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> List[TimeCorrectionOut]:
    try:
        if skip < 0 or limit <= 0:
            raise ValidationError(detail="Invalid pagination parameters")

        if user_id and user_id != current_user.user_id:
            await check_permissions([Permission.VIEW_TEAM_ATTENDANCE], current_user, db)

        query = select(TimeCorrections)
        target_user_id = user_id if user_id else current_user.user_id
        query = query.where(TimeCorrections.user_id == target_user_id)
        query = query.order_by(TimeCorrections.created_at.desc()).offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        
        result = await db.execute(query)
        corrections = result.scalars().all()

        logger.info(f"Retrieved {len(corrections)} time corrections for user_id: {target_user_id}")
        return [TimeCorrectionOut.model_validate(correction) for correction in corrections]

    except ValidationError as e:
        logger.error(f"Validation error in get_time_corrections for user_id {current_user.user_id}: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_time_corrections for user_id {current_user.user_id}: {str(e)}")
        raise DatabaseError(message="Database error retrieving time corrections", original_error=e)
    except Exception as e:
        logger.error(f"Unexpected error in get_time_corrections for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error retrieving time corrections"
        )

@router.put("/time-corrections/{correction_id}", 
            response_model=TimeCorrectionOut,
            dependencies=[Depends(require_permissions([Permission.APPROVE_LEAVE]))],
            summary="Approve/reject time correction", 
            description="Approve or reject a time correction request.")
async def approve_reject_time_correction(
    correction_id: int,
    approval_data: TimeCorrectionApproval,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> TimeCorrectionOut:
    try:
        if approval_data.status not in [CorrectionStatus.APPROVED, CorrectionStatus.REJECTED]:
            raise ValidationError(detail="Invalid status. Must be 'approved' or 'rejected'")

        query = select(TimeCorrections).where(TimeCorrections.correction_id == correction_id)
        result = await db.execute(query)
        correction = result.scalar_one_or_none()
        if not correction:
            raise ResourceNotFoundError(resource="Time correction", identifier=str(correction_id))

        if correction.status != CorrectionStatus.UNDER_REVIEW:
            raise AttendanceError(detail="Time correction has already been processed")

        correction.status = approval_data.status
        correction.approved_by = current_user.user_id
        correction.approved_at = datetime.now(timezone.utc)
        correction.updated_at = datetime.now(timezone.utc)

        if approval_data.status == CorrectionStatus.APPROVED:
            query = select(AttendanceRecords).where(AttendanceRecords.attendance_id == correction.attendance_id)
            result = await db.execute(query)
            record = result.scalar_one_or_none()
            if record:
                if correction.corrected_clock_in:
                    if correction.corrected_clock_in > datetime.now(timezone.utc):
                        raise ValidationError(detail="corrected_clock_in cannot be in the future")
                    record.clock_in_time = correction.corrected_clock_in
                if correction.corrected_clock_out:
                    if correction.corrected_clock_out > datetime.now(timezone.utc):
                        raise ValidationError(detail="corrected_clock_out cannot be in the future")
                    if correction.corrected_clock_in and correction.corrected_clock_out <= correction.corrected_clock_in:
                        raise ValidationError(detail="corrected_clock_out must be after corrected_clock_in")
                    record.clock_out_time = correction.corrected_clock_out
                record.updated_at = datetime.now(timezone.utc)
                db.add(record)

        db.add(correction)
        await db.commit()
        await db.refresh(correction)

        # Invalidate cache for attendance history
        await invalidate_cache_prefix(f"attendance_history:{correction.user_id}")

        logger.info(f"Time correction {correction_id} {approval_data.status} by user_id: {current_user.user_id}")
        return TimeCorrectionOut.model_validate(correction)

    except ValidationError as e:
        logger.error(f"Validation error in approve_reject_time_correction for correction_id {correction_id}: {str(e)}")
        raise
    except ResourceNotFoundError as e:
        logger.error(f"Resource not found in approve_reject_time_correction for correction_id {correction_id}: {str(e)}")
        raise
    except AttendanceError as e:
        logger.error(f"Attendance error in approve_reject_time_correction for correction_id {correction_id}: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in approve_reject_time_correction for correction_id {correction_id}: {str(e)}")
        raise DatabaseError(message="Database error processing time correction", original_error=e)
    except Exception as e:
        logger.error(f"Unexpected error in approve_reject_time_correction for correction_id {correction_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error processing time correction"
        )

@router.get("/summary", 
            response_model=List[AttendanceSummaryOut],
            summary="Get attendance summary", 
            description="Get attendance summary for current user or team (if authorized).")
async def get_attendance_summary(
    user_id: Optional[int] = None,
    start_date: date = date.today().replace(day=1),
    end_date: date = date.today(),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> List[AttendanceSummaryOut]:
    try:
        if start_date > end_date:
            raise ValidationError(detail="Start date cannot be after end date")
        if start_date > date.today() or end_date > date.today():
            raise ValidationError(detail="Start and end dates cannot be in the future")

        if user_id and user_id != current_user.user_id:
            await check_permissions([Permission.VIEW_TEAM_ATTENDANCE], current_user, db)

        target_user_id = user_id if user_id else current_user.user_id

        start_datetime = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_datetime = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)

        query = select(
            AttendanceRecords.user_id,
            Users.employee_id,
            func.concat(Users.first_name, ' ', Users.last_name).label('full_name'),
            AttendanceRecords.date,
            AttendanceRecords.status,
            AttendanceRecords.total_hours,
            AttendanceRecords.overtime_hours,
            AttendanceRecords.clock_in_time,
            AttendanceRecords.clock_out_time
        ).join(
            Users, Users.user_id == AttendanceRecords.user_id
        ).where(
            AttendanceRecords.user_id == target_user_id,
            AttendanceRecords.clock_in_time >= start_datetime,
            AttendanceRecords.clock_in_time <= end_datetime,
            AttendanceRecords.is_active == True,
            Users.is_active == True,
            Users.deleted_at == None
        ).order_by(AttendanceRecords.date.desc())

        result = await db.execute(query)
        records = result.fetchall()

        logger.info(f"Attendance summary retrieved for user_id: {target_user_id}")
        
        try:
            return [AttendanceSummaryOut(
                user_id=record.user_id,
                employee_id=record.employee_id,
                full_name=record.full_name,
                date=record.date,
                status=record.status,
                total_hours=str(record.total_hours) if record.total_hours is not None else None,
                overtime_hours=str(record.overtime_hours) if record.overtime_hours is not None else None,
                clock_in_time=record.clock_in_time,
                clock_out_time=record.clock_out_time
            ) for record in records]
        except ValueError as e:
            logger.error(f"Validation error in attendance summary serialization for user_id {target_user_id}: {str(e)}")
            raise ValidationError(detail=f"Data validation error: {str(e)}")

    except ValidationError as e:
        logger.error(f"Validation error in get_attendance_summary for user_id {target_user_id}: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_attendance_summary for user_id {target_user_id}: {str(e)}")
        raise DatabaseError(message="Database error retrieving attendance summary", original_error=e)
    except Exception as e:
        logger.error(f"Unexpected error in get_attendance_summary for user_id {target_user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error retrieving attendance summary"
        )

@router.get("/export/csv", 
            dependencies=[Depends(require_permissions([Permission.VIEW_OWN_ATTENDANCE]))],
            summary="Export attendance history as CSV", 
            description="Export attendance history as a CSV file.")
async def export_attendance_csv(
    background_tasks: BackgroundTasks,
    start_date: date = date.today().replace(day=1),
    end_date: date = date.today(),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> FileResponse:
    try:
        if start_date > end_date:
            raise ValidationError(detail="Start date cannot be after end date")
        if start_date > date.today() or end_date > date.today():
            raise ValidationError(detail="Start and end dates cannot be in the future")

        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == current_user.user_id,
            AttendanceRecords.clock_in_time >= start_date,
            AttendanceRecords.clock_in_time <= end_date,
            AttendanceRecords.is_active == True
        ).order_by(AttendanceRecords.clock_in_time.desc())
        
        result = await db.execute(query)
        records = result.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Record ID", "Date", "Clock In", "Clock Out", 
            "Status", "Total Hours", "Overtime Hours"
        ])
        
        for record in records:
            writer.writerow([
                record.attendance_id,
                record.date,
                record.clock_in_time,
                record.clock_out_time,
                record.status,
                record.total_hours,
                record.overtime_hours
            ])

        filename = f"attendance_{current_user.employee_id}_{start_date}_to_{end_date}.csv"
        async with aiofiles.open(filename, "w", encoding='utf-8') as f:
            await f.write(output.getvalue())

        background_tasks.add_task(_delete_file, filename)
        logger.info(f"Attendance CSV exported for user_id: {current_user.user_id}")
        return FileResponse(
            filename, 
            media_type="text/csv", 
            filename=f"attendance_export_{start_date}_to_{end_date}.csv"
        )

    except ValidationError as e:
        logger.error(f"Validation error in export_attendance_csv for user_id {current_user.user_id}: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in export_attendance_csv for user_id {current_user.user_id}: {str(e)}")
        raise DatabaseError(message="Database error exporting attendance CSV", original_error=e)
    except OSError as e:
        logger.error(f"File operation error in export_attendance_csv for user_id {current_user.user_id}: {str(e)}")
        raise FileUploadError(detail=f"File operation error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in export_attendance_csv for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error exporting attendance CSV"
        )

@router.get("/export/pdf", 
            dependencies=[Depends(require_permissions([Permission.VIEW_OWN_ATTENDANCE]))],
            summary="Export attendance history as PDF", 
            description="Export attendance history as a PDF file.")
async def export_attendance_pdf(
    background_tasks: BackgroundTasks,
    start_date: date = date.today().replace(day=1),
    end_date: date = date.today(),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> FileResponse:
    try:
        if start_date > end_date:
            raise ValidationError(detail="Start date cannot be after end date")
        if start_date > date.today() or end_date > date.today():
            raise ValidationError(detail="Start and end dates cannot be in the future")

        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == current_user.user_id,
            AttendanceRecords.clock_in_time >= start_date,
            AttendanceRecords.clock_in_time <= end_date,
            AttendanceRecords.is_active == True
        ).order_by(AttendanceRecords.clock_in_time.desc())
        
        result = await db.execute(query)
        records = result.scalars().all()

        filename = f"attendance_{current_user.employee_id}_{start_date}_to_{end_date}.pdf"
        data = [[
            "Record ID", "Date", "Clock In", "Clock Out", 
            "Status", "Total Hours", "Overtime Hours"
        ]]
        
        for record in records:
            data.append([
                str(record.attendance_id),
                str(record.date) if record.date else "",
                str(record.clock_in_time),
                str(record.clock_out_time) if record.clock_out_time else "",
                str(record.status) if record.status else "",
                str(record.total_hours) if record.total_hours else "",
                str(record.overtime_hours) if record.overtime_hours else ""
            ])

        await _generate_pdf(data, filename)
        background_tasks.add_task(_delete_file, filename)
        logger.info(f"Attendance PDF exported for user_id: {current_user.user_id}")
        return FileResponse(
            filename, 
            media_type="application/pdf", 
            filename=f"attendance_export_{start_date}_to_{end_date}.pdf"
        )

    except ValidationError as e:
        logger.error(f"Validation error in export_attendance_pdf for user_id {current_user.user_id}: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in export_attendance_pdf for user_id {current_user.user_id}: {str(e)}")
        raise DatabaseError(message="Database error exporting attendance PDF", original_error=e)
    except OSError as e:
        logger.error(f"File operation error in export_attendance_pdf for user_id {current_user.user_id}: {str(e)}")
        raise FileUploadError(detail=f"File operation error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in export_attendance_pdf for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error exporting attendance PDF"
        )