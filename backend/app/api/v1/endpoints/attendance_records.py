from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from datetime import datetime, timezone, date
from app.core.database import get_db
from app.models.attendance_records import AttendanceRecords
from app.models.time_corrections import TimeCorrections
from app.models.users import Users
from app.core.permissions import (
    check_permissions, 
    require_permissions,
    require_employee_permissions
)
from app.core.security import get_current_user
from app.core.config import settings
from app.core.enums import Permission, CorrectionStatus, AttendanceStatus
from app.schemas.attendance_record import AttendanceRecordOut
from app.schemas.time_correction import TimeCorrectionCreate, TimeCorrectionOut
from app.schemas.attendance_summary import AttendanceSummaryOut
import logging
import csv
import io
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attendance-records", tags=["Attendance Records"])

class ClockInOut(BaseModel):
    action: str  # 'clock_in' or 'clock_out'
    model_config = ConfigDict(from_attributes=True)

class TimeCorrectionApproval(BaseModel):
    status: str  # 'approved' or 'rejected'
    model_config = ConfigDict(from_attributes=True)

@router.post("/clock", 
             response_model=AttendanceRecordOut, 
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_employee_permissions())],
             summary="Clock in or out", 
             description="Record clock-in or clock-out for an employee.")
async def clock_in_out(
    clock_data: ClockInOut,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> AttendanceRecordOut:
    try:
        if clock_data.action not in ["clock_in", "clock_out"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Invalid action. Must be 'clock_in' or 'clock_out'"
            )

        if clock_data.action == "clock_in":
            # Check for existing active clock-in
            query = select(AttendanceRecords).where(
                AttendanceRecords.user_id == current_user.user_id,
                AttendanceRecords.clock_out_time == None,
                AttendanceRecords.is_active == True
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="You are already clocked in"
                )

            record = AttendanceRecords(
                user_id=current_user.user_id,
                clock_in_time=datetime.now(timezone.utc),
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
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, 
                    detail="No active clock-in found"
                )

            record.clock_out_time = datetime.now(timezone.utc)
            record.updated_at = datetime.now(timezone.utc)
            db.add(record)

        await db.commit()
        await db.refresh(record)

        logger.info(f"Clock {clock_data.action} recorded for user_id: {current_user.user_id}")
        return AttendanceRecordOut.model_validate(record)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording clock {clock_data.action} for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error processing clock action"
        )

@router.get("/history", 
            response_model=List[AttendanceRecordOut],
            dependencies=[Depends(require_permissions([Permission.VIEW_OWN_ATTENDANCE]))],
            summary="Get attendance history", 
            description="Retrieve attendance history for the current user with pagination.")
async def get_attendance_history(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> List[AttendanceRecordOut]:
    try:
        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == current_user.user_id,
            AttendanceRecords.is_active == True
        ).order_by(AttendanceRecords.created_at.desc()).offset(skip).limit(limit)
        
        result = await db.execute(query)
        records = result.scalars().all()

        logger.info(f"Retrieved {len(records)} attendance records for user_id: {current_user.user_id}")
        return [AttendanceRecordOut.model_validate(record) for record in records]

    except Exception as e:
        logger.error(f"Error retrieving attendance history for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error retrieving attendance history"
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
        # Verify attendance record exists and belongs to current user
        query = select(AttendanceRecords).where(
            AttendanceRecords.record_id == correction.attendance_id,
            AttendanceRecords.user_id == current_user.user_id,
            AttendanceRecords.is_active == True
        )
        result = await db.execute(query)
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Attendance record not found"
            )

        db_correction = TimeCorrections(
            record_id=correction.attendance_id,
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

        logger.info(f"Time correction requested for record_id: {correction.attendance_id}")
        return TimeCorrectionOut.model_validate(db_correction)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error requesting time correction: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error requesting time correction"
        )

@router.get("/time-corrections", 
            response_model=List[TimeCorrectionOut],
            summary="Get time correction requests", 
            description="Retrieve time correction requests for current user or team (if authorized).")
async def get_time_corrections(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> List[TimeCorrectionOut]:
    try:
        # Check permissions for viewing other users' corrections
        if user_id and user_id != current_user.user_id:
            await check_permissions([Permission.VIEW_TEAM_ATTENDANCE], current_user, db)

        query = select(TimeCorrections)
        target_user_id = user_id if user_id else current_user.user_id
        query = query.where(TimeCorrections.user_id == target_user_id)
        query = query.order_by(TimeCorrections.created_at.desc()).offset(skip).limit(limit)
        
        result = await db.execute(query)
        corrections = result.scalars().all()

        logger.info(f"Retrieved {len(corrections)} time corrections for user_id: {target_user_id}")
        return [TimeCorrectionOut.model_validate(correction) for correction in corrections]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving time corrections: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error retrieving time corrections"
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
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Invalid status. Must be 'approved' or 'rejected'"
            )

        query = select(TimeCorrections).where(TimeCorrections.correction_id == correction_id)
        result = await db.execute(query)
        correction = result.scalar_one_or_none()
        if not correction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Time correction not found"
            )

        if correction.status != CorrectionStatus.UNDER_REVIEW:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Time correction has already been processed"
            )

        correction.status = approval_data.status
        correction.approved_by = current_user.user_id
        correction.approved_at = datetime.now(timezone.utc)
        correction.updated_at = datetime.now(timezone.utc)

        # Apply corrections if approved
        if approval_data.status == CorrectionStatus.APPROVED:
            query = select(AttendanceRecords).where(AttendanceRecords.record_id == correction.record_id)
            result = await db.execute(query)
            record = result.scalar_one_or_none()
            if record:
                if correction.corrected_clock_in:
                    record.clock_in_time = correction.corrected_clock_in
                if correction.corrected_clock_out:
                    record.clock_out_time = correction.corrected_clock_out
                record.updated_at = datetime.now(timezone.utc)
                db.add(record)

        db.add(correction)
        await db.commit()
        await db.refresh(correction)

        logger.info(f"Time correction {correction_id} {approval_data.status} by user_id: {current_user.user_id}")
        return TimeCorrectionOut.model_validate(correction)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing time correction {correction_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error processing time correction"
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
        # Check permissions for viewing other users' summaries
        if user_id and user_id != current_user.user_id:
            await check_permissions([Permission.VIEW_TEAM_ATTENDANCE], current_user, db)

        target_user_id = user_id if user_id else current_user.user_id

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
            AttendanceRecords.clock_in_time >= start_date,
            AttendanceRecords.clock_in_time <= end_date,
            AttendanceRecords.is_active == True,
            Users.is_active == True,
            Users.deleted_at == None
        ).order_by(AttendanceRecords.date.desc())

        result = await db.execute(query)
        records = result.fetchall()

        logger.info(f"Attendance summary retrieved for user_id: {target_user_id}")
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving attendance summary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error retrieving attendance summary"
        )

@router.get("/export/csv", 
            dependencies=[Depends(require_permissions([Permission.VIEW_OWN_ATTENDANCE]))],
            summary="Export attendance history as CSV", 
            description="Export attendance history as a CSV file.")
async def export_attendance_csv(
    start_date: date = date.today().replace(day=1),
    end_date: date = date.today(),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> FileResponse:
    filename = None
    try:
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
                record.record_id,
                record.date,
                record.clock_in_time,
                record.clock_out_time,
                record.status,
                record.total_hours,
                record.overtime_hours
            ])

        filename = f"attendance_{current_user.employee_id}_{start_date}_to_{end_date}.csv"
        with open(filename, "w", newline='', encoding='utf-8') as f:
            f.write(output.getvalue())

        logger.info(f"Attendance CSV exported for user_id: {current_user.user_id}")
        return FileResponse(
            filename, 
            media_type="text/csv", 
            filename=f"attendance_export_{start_date}_to_{end_date}.csv"
        )

    except Exception as e:
        logger.error(f"Error exporting attendance CSV: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error exporting attendance CSV"
        )
    finally:
        if filename and os.path.exists(filename):
            os.remove(filename)

@router.get("/export/pdf", 
            dependencies=[Depends(require_permissions([Permission.VIEW_OWN_ATTENDANCE]))],
            summary="Export attendance history as PDF", 
            description="Export attendance history as a PDF file.")
async def export_attendance_pdf(
    start_date: date = date.today().replace(day=1),
    end_date: date = date.today(),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> FileResponse:
    filename = None
    try:
        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == current_user.user_id,
            AttendanceRecords.clock_in_time >= start_date,
            AttendanceRecords.clock_in_time <= end_date,
            AttendanceRecords.is_active == True
        ).order_by(AttendanceRecords.clock_in_time.desc())
        
        result = await db.execute(query)
        records = result.scalars().all()

        filename = f"attendance_{current_user.employee_id}_{start_date}_to_{end_date}.pdf"
        doc = SimpleDocTemplate(filename, pagesize=letter)
        elements = []

        data = [[
            "Record ID", "Date", "Clock In", "Clock Out", 
            "Status", "Total Hours", "Overtime Hours"
        ]]
        
        for record in records:
            data.append([
                str(record.record_id),
                str(record.date) if record.date else "",
                str(record.clock_in_time),
                str(record.clock_out_time) if record.clock_out_time else "",
                str(record.status) if record.status else "",
                str(record.total_hours) if record.total_hours else "",
                str(record.overtime_hours) if record.overtime_hours else ""
            ])

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
        elements.append(table)

        doc.build(elements)

        logger.info(f"Attendance PDF exported for user_id: {current_user.user_id}")
        return FileResponse(
            filename, 
            media_type="application/pdf", 
            filename=f"attendance_export_{start_date}_to_{end_date}.pdf"
        )

    except Exception as e:
        logger.error(f"Error exporting attendance PDF: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error exporting attendance PDF"
        )
    finally:
        if filename and os.path.exists(filename):
            os.remove(filename)