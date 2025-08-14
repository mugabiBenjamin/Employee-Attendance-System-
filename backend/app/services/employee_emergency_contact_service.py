from typing import List, Optional
from fastapi import HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.employee_emergency_contacts import EmployeeEmergencyContacts
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.schemas.employee_emergency_contact import EmployeeEmergencyContactCreate, EmployeeEmergencyContactUpdate, EmployeeEmergencyContactOut
from app.core.config import settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import UserNotFoundError, ResourceNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

async def create_emergency_contact(
    contact: EmployeeEmergencyContactCreate,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.MANAGE_EMPLOYEES]))
) -> EmployeeEmergencyContactOut:
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
            raise UserNotFoundError(user_id=contact.employee_id)

        # Create emergency contact
        db_contact = EmployeeEmergencyContacts(
            user_id=contact.employee_id,
            **EmployeeEmergencyContactCreate(**contact.model_dump(exclude={'employee_id'})).model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_contact)
        await db.commit()
        await db.refresh(db_contact)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="employee_emergency_contacts",
            record_id=db_contact.contact_id,
            old_values=None,
            new_values=db_contact.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Emergency contact created, contact_id: {db_contact.contact_id}, user_id: {contact.employee_id}")
        return EmployeeEmergencyContactOut.model_validate(db_contact)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating emergency contact: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating emergency contact"
        )

async def get_emergency_contact_by_id(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.MANAGE_EMPLOYEES]))
) -> Optional[EmployeeEmergencyContactOut]:
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
            raise ResourceNotFoundError(resource="Emergency contact", identifier=f"ID {contact_id}")

        return EmployeeEmergencyContactOut.model_validate(contact)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving emergency contact {contact_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving emergency contact"
        )

async def get_emergency_contacts_by_employee(
    employee_id: int,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.MANAGE_EMPLOYEES]))
) -> List[EmployeeEmergencyContactOut]:
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
            raise UserNotFoundError(user_id=employee_id)

        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.user_id == employee_id,
            EmployeeEmergencyContacts.is_active == True,
            EmployeeEmergencyContacts.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        contacts = result.scalars().all()

        logger.info(f"Retrieved {len(contacts)} emergency contacts for user_id: {employee_id}")
        return [EmployeeEmergencyContactOut.model_validate(contact) for contact in contacts]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving emergency contacts for user_id {employee_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving emergency contacts"
        )

async def update_emergency_contact(
    contact_id: int,
    contact_update: EmployeeEmergencyContactUpdate,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.MANAGE_EMPLOYEES]))
) -> EmployeeEmergencyContactOut:
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
            raise ResourceNotFoundError(resource="Emergency contact", identifier=f"ID {contact_id}")

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
            action=SystemAction.UPDATE,
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
        return EmployeeEmergencyContactOut.model_validate(db_contact)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating emergency contact {contact_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating emergency contact"
        )

async def delete_emergency_contact(
    contact_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.MANAGE_EMPLOYEES]))
) -> None:
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
            raise ResourceNotFoundError(resource="Emergency contact", identifier=f"ID {contact_id}")

        db_contact.is_active = False
        db_contact.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.DELETE,
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