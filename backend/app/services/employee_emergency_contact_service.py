from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict
from app.models.employee_emergency_contacts import EmployeeEmergencyContacts
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.schemas.employee_emergency_contact import EmergencyContactCreate, EmergencyContactUpdate, EmergencyContactOut
from app.core.config import settings
from app.core.enums import SystemAction
import logging

logger = logging.getLogger(__name__)

class EmergencyContactCreateInternal(BaseModel):
    employee_id: int
    contact_name: str
    relationship: str
    phone_number: str
    alternate_phone_number: Optional[str] = None
    email: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

async def create_emergency_contact(db: AsyncSession, contact: EmergencyContactCreate, current_user: Users) -> EmergencyContactOut:
    """
    Create a new emergency contact for an employee with validation and logging.
    """
    try:
        # Validate employee_id
        query = select(Users).where(
            Users.user_id == contact.employee_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Employee not found"
            )

        # Create emergency contact
        db_contact = EmployeeEmergencyContacts(
            **EmergencyContactCreateInternal(**contact.model_dump()).model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_contact)
        await db.commit()
        await db.refresh(db_contact)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.EMERGENCY_CONTACT_CREATED,
            table_affected="employee_emergency_contacts",
            record_id=db_contact.contact_id,
            old_values=None,
            new_values=db_contact.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Emergency contact created, contact_id: {db_contact.contact_id}, employee_id: {contact.employee_id}")
        return EmergencyContactOut.model_validate(db_contact)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating emergency contact: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating emergency contact"
        )

async def get_emergency_contact_by_id(db: AsyncSession, contact_id: int) -> Optional[EmergencyContactOut]:
    """
    Retrieve an emergency contact by ID.
    """
    try:
        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active == True,
            EmployeeEmergencyContacts.deleted_at == None
        )
        result = await db.execute(query)
        contact = result.scalar_one_or_none()

        if not contact:
            return None

        return EmergencyContactOut.model_validate(contact)

    except Exception as e:
        logger.error(f"Error retrieving emergency contact {contact_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving emergency contact"
        )

async def get_emergency_contacts_by_employee(db: AsyncSession, employee_id: int, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[EmergencyContactOut]:
    """
    Retrieve a list of emergency contacts for an employee with pagination.
    """
    try:
        query = select(Users).where(
            Users.user_id == employee_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Employee not found"
            )

        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.employee_id == employee_id,
            EmployeeEmergencyContacts.is_active == True,
            EmployeeEmergencyContacts.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        contacts = result.scalars().all()

        logger.info(f"Retrieved {len(contacts)} emergency contacts for employee_id: {employee_id}")
        return [EmergencyContactOut.model_validate(contact) for contact in contacts]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving emergency contacts for employee_id {employee_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving emergency contacts"
        )

async def update_emergency_contact(db: AsyncSession, contact_id: int, contact_update: EmergencyContactUpdate, current_user: Users) -> EmergencyContactOut:
    """
    Update an emergency contact with validation and logging.
    """
    try:
        # Retrieve emergency contact
        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active == True,
            EmployeeEmergencyContacts.deleted_at == None
        )
        result = await db.execute(query)
        db_contact = result.scalar_one_or_none()

        if not db_contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Emergency contact not found"
            )

        # Store old values for logging
        old_values = db_contact.__dict__.copy()

        # Apply updates
        update_data = contact_update.model_dump(exclude_none=True)
        for key, value in update_data.items():
            setattr(db_contact, key, value)

        db_contact.updated_at = datetime.now(timezone.utc)
        db.add(db_contact)
        await db.commit()
        await db.refresh(db_contact)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.EMERGENCY_CONTACT_UPDATED,
            table_affected="employee_emergency_contacts",
            record_id=contact_id,
            old_values=old_values,
            new_values=db_contact.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Emergency contact updated, contact_id: {contact_id}")
        return EmergencyContactOut.model_validate(db_contact)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating emergency contact {contact_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating emergency contact"
        )

async def delete_emergency_contact(db: AsyncSession, contact_id: int, current_user: Users) -> None:
    """
    Soft delete an emergency contact with logging.
    """
    try:
        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active == True,
            EmployeeEmergencyContacts.deleted_at == None
        )
        result = await db.execute(query)
        db_contact = result.scalar_one_or_none()

        if not db_contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Emergency contact not found"
            )

        db_contact.is_active = False
        db_contact.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.EMERGENCY_CONTACT_DELETED,
            table_affected="employee_emergency_contacts",
            record_id=contact_id,
            old_values=db_contact.__dict__,
            new_values=None,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Emergency contact soft deleted, contact_id: {contact_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting emergency contact {contact_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting emergency contact"
        )