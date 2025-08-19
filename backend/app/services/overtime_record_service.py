from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, date
from app.models.overtime_records import OvertimeRecords
from app.models.users import Users
from app.models.attendance_records import AttendanceRecords
from app.models.employee_hierarchy import EmployeeHierarchy
from app.schemas.overtime_record import OvertimeRecordCreate, OvertimeRecordUpdate, OvertimeRecordOut, OvertimeRecordApproval
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission, OvertimeStatus
from app.core.mail import send_email
from app.core.exceptions import UserNotFoundError, OvertimeRecordNotFoundError, ValidationError, AttendanceRecordNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_user_exists
from app.services.system_log_service import create_system_log
from app.schemas.system_log import SystemLogCreate
import logging

logger = logging.getLogger(__name__)

async def validate_attendance_record_exists(db: AsyncSession, attendance_id: int, request_id: Optional[str] = None) -> None:
    """Validate that an attendance record exists."""
    query = select(AttendanceRecords).where(
        AttendanceRecords.attendance_id == attendance_id,
        AttendanceRecords.is_active == True
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
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.CREATE_OVERTIME_RECORD]))
) -> OvertimeRecordOut:
    """Create an overtime record with validation, logging, and email notification to manager."""
    try:
        await validate_user_exists(db, overtime.user_id, request_id)

        if not any(p in current_user.permissions for p in [Permission.MANAGE_OVERTIME, Permission.CREATE_ALL_OVERTIME]) and overtime.user_id != current_user.user_id:
            raise ValidationError(detail="Not authorized to create overtime record for this user")

        # Find corresponding attendance record
        query = select(AttendanceRecords).where(
            AttendanceRecords.user_id == overtime.user_id,
            AttendanceRecords.date == overtime.date,
            AttendanceRecords.is_active == True
        )
        result = await db.execute(query)
        attendance = result.scalar_one_or_none()
        if not attendance:
            raise AttendanceRecordNotFoundError(detail=f"No attendance record found for user_id {overtime.user_id} on {overtime.date}")

        query = select(OvertimeRecords).where(
            OvertimeRecords.user_id == overtime.user_id,
            OvertimeRecords.date == overtime.date,
            OvertimeRecords.is_active == True,
            OvertimeRecords.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ValidationError(detail="Overtime record already exists for this date")

        overtime_rate = overtime.overtime_rate or 1.5
        db_overtime = OvertimeRecords(
            attendance_id=attendance.attendance_id,
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

        # Check for threshold and notify manager
        if overtime.overtime_hours > settings.OVERTIME_THRESHOLD:
            query = select(Users).join(
                EmployeeHierarchy,
                EmployeeHierarchy.manager_id == Users.user_id
            ).where(
                EmployeeHierarchy.employee_id == overtime.user_id,
                EmployeeHierarchy.is_active == True,
                EmployeeHierarchy.deleted_at == None
            )
            result = await db.execute(query)
            manager = result.scalar_one_or_none()
            if manager:
                await send_email(
                    to_email=manager.email,
                    subject="Overtime Threshold Alert",
                    body=(
                        f"Employee {current_user.first_name} {current_user.last_name} recorded {overtime.overtime_hours} overtime hours on {overtime.date}.\n"
                        f"This exceeds the threshold of {settings.OVERTIME_THRESHOLD} hours."
                    ),
                    request_id=request_id
                )

        # Invalidate cache
        await invalidate_cache_prefix("overtime_records")
        await invalidate_cache_prefix(f"user:{overtime.user_id}")
        logger.debug(f"Cache cleared for overtime_records and user {overtime.user_id}")

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
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_OVERTIME_RECORD, Permission.VIEW_OWN_OVERTIME_RECORD]))
) -> OvertimeRecordOut:
    """Retrieve an overtime record by ID."""
    try:
        if overtime_id <= 0:
            raise ValidationError(detail="Invalid overtime ID")

        cache_key = f"overtime_record:{overtime_id}"
        cached_record = await get_cache(cache_key)
        if cached_record:
            return OvertimeRecordOut(**cached_record)

        query = select(OvertimeRecords).where(
            OvertimeRecords.overtime_id == overtime_id,
            OvertimeRecords.is_active == True,
            OvertimeRecords.deleted_at == None
        )
        if not any(p in current_user.permissions for p in [Permission.VIEW_OVERTIME_RECORD, Permission.MANAGE_OVERTIME]):
            query = query.join(
                EmployeeHierarchy,
                EmployeeHierarchy.employee_id == OvertimeRecords.user_id,
                isouter=True
            ).where(
                (OvertimeRecords.user_id == current_user.user_id) |
                (EmployeeHierarchy.manager_id == current_user.user_id)
            )
        result = await db.execute(query)
        overtime = result.scalar_one_or_none()

        if not overtime:
            raise OvertimeRecordNotFoundError(overtime_id=overtime_id)

        record_dict = OvertimeRecordOut.model_validate(overtime).model_dump()
        await set_cache(cache_key, record_dict, ttl=300)

        logger.info(
            f"Retrieved overtime record, overtime_id: {overtime_id}",
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
        logger.error(f"Error retrieving overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving overtime record")

async def get_user_overtime_records(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_OVERTIME_RECORD, Permission.VIEW_OWN_OVERTIME_RECORD]))
) -> List[OvertimeRecordOut]:
    """Retrieve a list of overtime records for a user with optional date range and pagination."""
    try:
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")
        if start_date and end_date and start_date > end_date:
            raise ValidationError(detail="Start date must be on or before end date")

        await validate_user_exists(db, user_id, request_id)

        if not any(p in current_user.permissions for p in [Permission.VIEW_OVERTIME_RECORD, Permission.MANAGE_OVERTIME]) and user_id != current_user.user_id:
            query = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == user_id,
                EmployeeHierarchy.manager_id == current_user.user_id,
                EmployeeHierarchy.is_active == True,
                EmployeeHierarchy.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise ValidationError(detail="Not authorized to view overtime records for this user")

        cache_key = f"overtime_records_user:{user_id}:{start_date or 'all'}:{end_date or 'all'}:{skip}:{limit or settings.DEFAULT_PAGE_SIZE}"
        cached_records = await get_cache(cache_key)
        if cached_records:
            return [OvertimeRecordOut(**r) for r in cached_records]

        query = select(OvertimeRecords).where(
            OvertimeRecords.user_id == user_id,
            OvertimeRecords.is_active == True,
            OvertimeRecords.deleted_at == None
        )
        if start_date:
            query = query.where(OvertimeRecords.date >= start_date)
        if end_date:
            query = query.where(OvertimeRecords.date <= end_date)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        overtime_records = result.scalars().all()

        records_dict = [OvertimeRecordOut.model_validate(r).model_dump() for r in overtime_records]
        await set_cache(cache_key, records_dict, ttl=300)

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
        logger.error(f"Error retrieving overtime records for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving overtime records")

async def get_team_overtime_records(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_TEAM_OVERTIME_RECORDS]))
) -> List[OvertimeRecordOut]:
    """Retrieve overtime records for a manager's team with optional date range and pagination."""
    try:
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")
        if start_date and end_date and start_date > end_date:
            raise ValidationError(detail="Start date must be on or before end date")

        cache_key = f"overtime_records_team:{current_user.user_id}:{start_date or 'all'}:{end_date or 'all'}:{skip}:{limit or settings.DEFAULT_PAGE_SIZE}"
        cached_records = await get_cache(cache_key)
        if cached_records:
            return [OvertimeRecordOut(**r) for r in cached_records]

        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.manager_id == current_user.user_id,
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
        result = await db.execute(query)
        team = result.scalars().all()
        employee_ids = [emp.employee_id for emp in team]

        if not employee_ids:
            return []

        query = select(OvertimeRecords).where(
            OvertimeRecords.user_id.in_(employee_ids),
            OvertimeRecords.is_active == True,
            OvertimeRecords.deleted_at == None
        )
        if start_date:
            query = query.where(OvertimeRecords.date >= start_date)
        if end_date:
            query = query.where(OvertimeRecords.date <= end_date)

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        overtime_records = result.scalars().all()

        records_dict = [OvertimeRecordOut.model_validate(r).model_dump() for r in overtime_records]
        await set_cache(cache_key, records_dict, ttl=300)

        logger.info(
            f"Retrieved {len(overtime_records)} overtime records for manager_id: {current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [OvertimeRecordOut.model_validate(record) for record in overtime_records]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving team overtime records for manager_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving team overtime records")

async def update_overtime_record(
    overtime_id: int,
    overtime_update: OvertimeRecordUpdate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.UPDATE_OVERTIME]))
) -> OvertimeRecordOut:
    """Update an overtime record with validation, logging, and cache clearing."""
    try:
        if overtime_id <= 0:
            raise ValidationError(detail="Invalid overtime ID")

        query = select(OvertimeRecords).where(
            OvertimeRecords.overtime_id == overtime_id,
            OvertimeRecords.is_active == True,
            OvertimeRecords.deleted_at == None
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

        # Invalidate cache
        await invalidate_cache_prefix("overtime_records")
        await invalidate_cache_prefix(f"user:{db_overtime.user_id}")
        logger.debug(f"Cache cleared for overtime_records and user {db_overtime.user_id}")

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
            f"Overtime record updated, overtime_id: {overtime_id}",
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
        logger.error(f"Error updating overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating overtime record")

async def approve_overtime_record(
    record_id: int,
    approval: OvertimeRecordApproval,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.APPROVE_OVERTIME]))
) -> OvertimeRecordOut:
    """Approve or reject an overtime record with logging and notification."""
    try:
        if record_id <= 0:
            raise ValidationError(detail="Invalid overtime ID")

        query = select(OvertimeRecords).where(
            OvertimeRecords.overtime_id == record_id,
            OvertimeRecords.is_active == True,
            OvertimeRecords.deleted_at == None
        )
        result = await db.execute(query)
        overtime = result.scalar_one_or_none()
        if not overtime:
            raise OvertimeRecordNotFoundError(overtime_id=record_id)

        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.employee_id == overtime.user_id,
            EmployeeHierarchy.manager_id == current_user.user_id,
            EmployeeHierarchy.is_active == True,
            EmployeeHierarchy.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
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

        # Invalidate cache
        await invalidate_cache_prefix("overtime_records")
        await invalidate_cache_prefix(f"user:{overtime.user_id}")
        logger.debug(f"Cache cleared for overtime_records and user {overtime.user_id}")

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

        # Notify employee
        query = select(Users).where(Users.user_id == overtime.user_id)
        result = await db.execute(query)
        employee = result.scalar_one_or_none()
        if employee:
            await send_email(
                to_email=employee.email,
                subject=f"Overtime Record {approval.status.value.capitalize()} (ID: {overtime.overtime_id})",
                body=(
                    f"Dear {employee.first_name},\n\n"
                    f"Your overtime record (ID: {overtime.overtime_id}) has been {approval.status.value.lower()}.\n"
                    f"Details:\n"
                    f"Date: {overtime.date}\n"
                    f"Hours: {overtime.overtime_hours}\n"
                    f"Comments: {approval.comments or 'None'}\n\n"
                    f"Please contact HR for any questions.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )

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
        logger.error(f"Error approving overtime record {record_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing overtime record")

async def delete_overtime_record(
    overtime_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.DELETE_OVERTIME]))
) -> None:
    """Soft delete an overtime record with logging and cache clearing."""
    try:
        if overtime_id <= 0:
            raise ValidationError(detail="Invalid overtime ID")

        query = select(OvertimeRecords).where(
            OvertimeRecords.overtime_id == overtime_id,
            OvertimeRecords.is_active == True,
            OvertimeRecords.deleted_at == None
        )
        result = await db.execute(query)
        db_overtime = result.scalar_one_or_none()

        if not db_overtime:
            raise OvertimeRecordNotFoundError(overtime_id=overtime_id)

        db_overtime.is_active = False
        db_overtime.deleted_at = datetime.now(timezone.utc)
        db_overtime.updated_at = datetime.now(timezone.utc)
        db.add(db_overtime)
        await db.commit()

        # Invalidate cache
        await invalidate_cache_prefix("overtime_records")
        await invalidate_cache_prefix(f"user:{db_overtime.user_id}")
        logger.debug(f"Cache cleared for overtime_records and user {db_overtime.user_id}")

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
            f"Overtime record soft deleted, overtime_id: {overtime_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except OvertimeRecordNotFoundError as e:
        logger.error(f"Overtime record not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting overtime record {overtime_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting overtime record")