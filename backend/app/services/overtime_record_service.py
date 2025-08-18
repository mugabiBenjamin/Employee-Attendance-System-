from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, date
from app.models.overtime_records import OvertimeRecords
from app.models.users import Users
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.system_logs import SystemLogs
from app.schemas.overtime_record import OvertimeRecordCreate, OvertimeRecordUpdate, OvertimeRecordOut, OvertimeRecordApproval
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission, OvertimeStatus
from app.core.mail import send_email
from app.core.exceptions import UserNotFoundError, OvertimeRecordNotFoundError, ValidationError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

async def create_overtime_record(
    overtime: OvertimeRecordCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.CREATE_OVERTIME_RECORD]))
) -> OvertimeRecordOut:
    """Create an overtime record with validation, logging, and email notification to manager."""
    try:
        query = select(Users).where(
            Users.user_id == overtime.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise UserNotFoundError(user_id=overtime.user_id)

        if not any(p in current_user.permissions for p in [Permission.MANAGE_OVERTIME, Permission.CREATE_ALL_OVERTIME]) and overtime.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to create overtime record for this user"
            )

        query = select(OvertimeRecords).where(
            OvertimeRecords.user_id == overtime.user_id,
            OvertimeRecords.date == overtime.date,
            OvertimeRecords.is_active.is_(True),
            OvertimeRecords.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ValidationError(detail="Overtime record already exists for this date")

        settings = get_settings()
        if overtime.overtime_hours > settings.OVERTIME_THRESHOLD:
            query = select(Users).join(
                EmployeeHierarchy,
                EmployeeHierarchy.manager_id == Users.user_id
            ).where(
                EmployeeHierarchy.employee_id == overtime.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
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
                    )
                )

        db_overtime = OvertimeRecords(
            user_id=overtime.user_id,
            date=overtime.date,
            overtime_hours=overtime.overtime_hours,
            overtime_rate=1.5,
            overtime_amount=overtime.overtime_hours * 1.5,
            description=overtime.description,
            status=OvertimeStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_overtime)
        await db.commit()
        await db.refresh(db_overtime)

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_OVERTIME_RECORD,
            table_affected="overtime_records",
            record_id=db_overtime.overtime_id,
            old_values=None,
            new_values=db_overtime.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Overtime record created, overtime_id: {db_overtime.overtime_id}, user_id: {overtime.user_id}")
        return OvertimeRecordOut.model_validate(db_overtime)

    except (UserNotFoundError, ValidationError, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error creating overtime record for user_id {overtime.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating overtime record"
        )

async def get_overtime_record(
    overtime_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.VIEW_OVERTIME_RECORD, Permission.VIEW_OWN_OVERTIME_RECORD]))
) -> OvertimeRecordOut:
    """Retrieve an overtime record by ID."""
    try:
        query = select(OvertimeRecords).where(
            OvertimeRecords.overtime_id == overtime_id,
            OvertimeRecords.is_active.is_(True),
            OvertimeRecords.deleted_at.is_(None)
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

        logger.info(f"Retrieved overtime record, overtime_id: {overtime_id}, user_id: {current_user.user_id}")
        return OvertimeRecordOut.model_validate(overtime)

    except OvertimeRecordNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error retrieving overtime record {overtime_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving overtime record"
        )

async def get_user_overtime_records(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_OVERTIME_RECORD, Permission.VIEW_OWN_OVERTIME_RECORD]))
) -> List[OvertimeRecordOut]:
    """Retrieve a list of overtime records for a user with optional date range and pagination."""
    try:
        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise UserNotFoundError(user_id=user_id)

        if not any(p in current_user.permissions for p in [Permission.VIEW_OVERTIME_RECORD, Permission.MANAGE_OVERTIME]) and user_id != current_user.user_id:
            query = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == user_id,
                EmployeeHierarchy.manager_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view overtime records for this user"
                )

        query = select(OvertimeRecords).where(
            OvertimeRecords.user_id == user_id,
            OvertimeRecords.is_active.is_(True),
            OvertimeRecords.deleted_at.is_(None)
        )
        if start_date:
            query = query.where(OvertimeRecords.date >= start_date)
        if end_date:
            query = query.where(OvertimeRecords.date <= end_date)

        query = query.offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        result = await db.execute(query)
        overtime_records = result.scalars().all()

        logger.info(f"Retrieved {len(overtime_records)} overtime records for user_id: {user_id}")
        return [OvertimeRecordOut.model_validate(record) for record in overtime_records]

    except (UserNotFoundError, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error retrieving overtime records for user_id {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving overtime records"
        )

async def get_team_overtime_records(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_TEAM_OVERTIME_RECORDS]))
) -> List[OvertimeRecordOut]:
    """Retrieve overtime records for a manager's team with optional date range and pagination."""
    try:
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.manager_id == current_user.user_id,
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
        if start_date:
            query = query.where(OvertimeRecords.date >= start_date)
        if end_date:
            query = query.where(OvertimeRecords.date <= end_date)

        query = query.offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        result = await db.execute(query)
        overtime_records = result.scalars().all()

        logger.info(f"Retrieved {len(overtime_records)} overtime records for manager_id: {current_user.user_id}")
        return [OvertimeRecordOut.model_validate(record) for record in overtime_records]

    except Exception as e:
        logger.error(f"Error retrieving team overtime records for manager_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving team overtime records"
        )

async def approve_overtime_record(
    record_id: int,
    approval: OvertimeRecordApproval,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.APPROVE_OVERTIME]))
) -> OvertimeRecordOut:
    """Approve or reject an overtime record with logging and notification."""
    try:
        query = select(OvertimeRecords).where(
            OvertimeRecords.overtime_id == record_id,
            OvertimeRecords.is_active.is_(True),
            OvertimeRecords.deleted_at.is_(None)
        )
        result = await db.execute(query)
        overtime = result.scalar_one_or_none()
        if not overtime:
            raise OvertimeRecordNotFoundError(overtime_id=record_id)

        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.employee_id == overtime.user_id,
            EmployeeHierarchy.manager_id == current_user.user_id,
            EmployeeHierarchy.is_active.is_(True),
            EmployeeHierarchy.deleted_at.is_(None)
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

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.APPROVE_OVERTIME_RECORD,
            table_affected="overtime_records",
            record_id=overtime.overtime_id,
            old_values=old_values,
            new_values=overtime.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

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
                )
            )

        logger.info(f"Overtime record {record_id} {approval.status.value} by user_id: {current_user.user_id}")
        return OvertimeRecordOut.model_validate(overtime)

    except (OvertimeRecordNotFoundError, ValidationError):
        raise
    except Exception as e:
        logger.error(f"Error approving overtime record {record_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing overtime record"
        )