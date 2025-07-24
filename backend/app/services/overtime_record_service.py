from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, date
from pydantic import BaseModel, ConfigDict
from app.models.overtime_records import OvertimeRecords
from app.models.users import Users
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.system_logs import SystemLogs
from app.schemas.overtime_record import OvertimeRecordCreate, OvertimeRecordOut
from app.core.config import settings
from app.core.enums import SystemAction
from app.core.mail import send_email_notification
import logging

logger = logging.getLogger(__name__)

class OvertimeRecordCreateInternal(BaseModel):
    user_id: int
    date: date
    overtime_hours: float
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

async def create_overtime_record(db: AsyncSession, overtime: OvertimeRecordCreate, current_user: Users) -> OvertimeRecordOut:
    """
    Create an overtime record with validation, logging, and email notification to manager.
    """
    try:
        # Validate user
        query = select(Users).where(
            Users.user_id == overtime.user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Check for existing record on same date
        query = select(OvertimeRecords).where(
            OvertimeRecords.user_id == overtime.user_id,
            OvertimeRecords.date == overtime.date,
            OvertimeRecords.is_active == True,
            OvertimeRecords.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Overtime record already exists for this date"
            )

        # Check if overtime exceeds threshold (configurable in settings)
        if overtime.overtime_hours > settings.OVERTIME_THRESHOLD:
            # Send alert to manager
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
                await send_email_notification(
                    to_email=manager.email,
                    subject="Overtime Alert",
                    body=f"Employee {current_user.first_name} {current_user.last_name} recorded {overtime.overtime_hours} overtime hours on {overtime.date}."
                )

        # Create overtime record
        db_overtime = OvertimeRecords(
            **OvertimeRecordCreateInternal(**overtime.model_dump()).model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_overtime)
        await db.commit()
        await db.refresh(db_overtime)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.OVERTIME_RECORDED,
            table_affected="overtime_records",
            record_id=db_overtime.overtime_id,
            old_values=None,
            new_values=db_overtime.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Overtime record created, overtime_id: {db_overtime.overtime_id}, user_id: {overtime.user_id}")
        return OvertimeRecordOut.model_validate(db_overtime)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating overtime record for user_id {overtime.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating overtime record"
        )

async def get_overtime_record_by_id(db: AsyncSession, overtime_id: int) -> Optional[OvertimeRecordOut]:
    """
    Retrieve an overtime record by ID.
    """
    try:
        query = select(OvertimeRecords).where(
            OvertimeRecords.overtime_id == overtime_id,
            OvertimeRecords.is_active == True,
            OvertimeRecords.deleted_at == None
        )
        result = await db.execute(query)
        overtime = result.scalar_one_or_none()

        if not overtime:
            return None

        return OvertimeRecordOut.model_validate(overtime)

    except Exception as e:
        logger.error(f"Error retrieving overtime record {overtime_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving overtime record"
        )

async def get_user_overtime_records(db: AsyncSession, user_id: int, start_date: Optional[date] = None, end_date: Optional[date] = None, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[OvertimeRecordOut]:
    """
    Retrieve a list of overtime records for a user with optional date range and pagination.
    """
    try:
        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        query = select(OvertimeRecords).where(
            OvertimeRecords.user_id == user_id,
            OvertimeRecords.is_active == True,
            OvertimeRecords.deleted_at == None
        )
        if start_date:
            query = query.where(OvertimeRecords.date >= start_date)
        if end_date:
            query = query.where(OvertimeRecords.date <= end_date)

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        overtime_records = result.scalars().all()

        logger.info(f"Retrieved {len(overtime_records)} overtime records for user_id: {user_id}")
        return [OvertimeRecordOut.model_validate(record) for record in overtime_records]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving overtime records for user_id {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving overtime records"
        )

async def get_team_overtime_records(db: AsyncSession, manager: Users, start_date: Optional[date] = None, end_date: Optional[date] = None, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[OvertimeRecordOut]:
    """
    Retrieve overtime records for a manager's team with optional date range and pagination.
    """
    try:
        # Get employees under the manager
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.manager_id == manager.user_id,
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

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        overtime_records = result.scalars().all()

        logger.info(f"Retrieved {len(overtime_records)} overtime records for manager_id: {manager.user_id}")
        return [OvertimeRecordOut.model_validate(record) for record in overtime_records]

    except Exception as e:
        logger.error(f"Error retrieving team overtime records for manager_id {manager.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving team overtime records"
        )