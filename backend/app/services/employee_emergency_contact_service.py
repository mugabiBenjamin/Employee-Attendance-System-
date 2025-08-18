from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.employee_emergency_contacts import EmployeeEmergencyContacts
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.schemas.employee_emergency_contact import EmployeeEmergencyContactCreate, EmployeeEmergencyContactUpdate, EmployeeEmergencyContactOut
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import UserNotFoundError, EmployeeEmergencyContactNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

async def create_emergency_contact(
    contact: EmployeeEmergencyContactCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.CREATE_EMERGENCY_CONTACT]))
) -> EmployeeEmergencyContactOut:
    """Create a new emergency contact for an employee with validation and logging."""
    try:
        query = select(Users).where(
            Users.user_id == contact.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise UserNotFoundError(user_id=contact.user_id)

        db_contact = EmployeeEmergencyContacts(
            **contact.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_contact)
        await db.commit()
        await db.refresh(db_contact)

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_EMERGENCY_CONTACT,
            table_affected="employee_emergency_contacts",
            record_id=db_contact.contact_id,
            old_values=None,
            new_values=db_contact.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Emergency contact created, contact_id: {db_contact.contact_id}, user_id: {contact.user_id}")
        return EmployeeEmergencyContactOut.model_validate(db_contact)

    except UserNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error creating emergency contact for user_id {contact.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating emergency contact"
        )

async def get_emergency_contact(
    contact_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.VIEW_EMERGENCY_CONTACT, Permission.VIEW_OWN_EMERGENCY_CONTACT]))
) -> EmployeeEmergencyContactOut:
    """Retrieve an emergency contact by ID."""
    try:
        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active.is_(True),
            EmployeeEmergencyContacts.deleted_at.is_(None)
        )
        result = await db.execute(query)
        contact = result.scalar_one_or_none()

        if not contact:
            raise EmployeeEmergencyContactNotFoundError(contact_id=contact_id)

        if not any(p in current_user.permissions for p in [Permission.VIEW_EMERGENCY_CONTACT, Permission.MANAGE_EMPLOYEES]) and contact.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this emergency contact"
            )

        return EmployeeEmergencyContactOut.model_validate(contact)

    except (EmployeeEmergencyContactNotFoundError, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error retrieving emergency contact {contact_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving emergency contact"
        )

async def list_emergency_contacts(
    user_id: Optional[int],
    skip: int = 0,
    limit: int = 50,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_EMERGENCY_CONTACT, Permission.VIEW_OWN_EMERGENCY_CONTACT]))
) -> List[EmployeeEmergencyContactOut]:
    """Retrieve a list of emergency contacts for an employee with pagination."""
    try:
        target_user_id = user_id
        if not any(p in current_user.permissions for p in [Permission.VIEW_EMERGENCY_CONTACT, Permission.MANAGE_EMPLOYEES]):
            target_user_id = current_user.user_id

        if target_user_id:
            query = select(Users).where(
                Users.user_id == target_user_id,
                Users.is_active.is_(True),
                Users.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise UserNotFoundError(user_id=target_user_id)

        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.is_active.is_(True),
            EmployeeEmergencyContacts.deleted_at.is_(None)
        )
        if target_user_id:
            query = query.where(EmployeeEmergencyContacts.user_id == target_user_id)

        query = query.offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        result = await db.execute(query)
        contacts = result.scalars().all()

        logger.info(f"Retrieved {len(contacts)} emergency contacts for user_id: {target_user_id or 'all'}")
        return [EmployeeEmergencyContactOut.model_validate(contact) for contact in contacts]

    except UserNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error retrieving emergency contacts for user_id {target_user_id or 'all'}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving emergency contacts"
        )

async def update_emergency_contact(
    contact_id: int,
    contact_update: EmployeeEmergencyContactUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.UPDATE_EMERGENCY_CONTACT, Permission.VIEW_OWN_EMERGENCY_CONTACT]))
) -> EmployeeEmergencyContactOut:
    """Update an emergency contact with validation and logging."""
    try:
        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active.is_(True),
            EmployeeEmergencyContacts.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_contact = result.scalar_one_or_none()

        if not db_contact:
            raise EmployeeEmergencyContactNotFoundError(contact_id=contact_id)

        if not any(p in current_user.permissions for p in [Permission.UPDATE_EMERGENCY_CONTACT, Permission.MANAGE_EMPLOYEES]) and db_contact.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this emergency contact"
            )

        old_values = db_contact.__dict__.copy()
        update_data = contact_update.model_dump(exclude_none=True)
        for key, value in update_data.items():
            setattr(db_contact, key, value)

        db_contact.updated_at = datetime.now(timezone.utc)
        db.add(db_contact)
        await db.commit()
        await db.refresh(db_contact)

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_EMERGENCY_CONTACT,
            table_affected="employee_emergency_contacts",
            record_id=contact_id,
            old_values=old_values,
            new_values=db_contact.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Emergency contact updated, contact_id: {contact_id}")
        return EmployeeEmergencyContactOut.model_validate(db_contact)

    except (EmployeeEmergencyContactNotFoundError, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error updating emergency contact {contact_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating emergency contact"
        )

async def delete_emergency_contact(
    contact_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_permissions([Permission.DELETE_EMERGENCY_CONTACT]))
) -> None:
    """Soft delete an emergency contact with logging."""
    try:
        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active.is_(True),
            EmployeeEmergencyContacts.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_contact = result.scalar_one_or_none()

        if not db_contact:
            raise EmployeeEmergencyContactNotFoundError(contact_id=contact_id)

        db_contact.is_active = False
        db_contact.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_EMERGENCY_CONTACT,
            table_affected="employee_emergency_contacts",
            record_id=contact_id,
            old_values=db_contact.__dict__,
            new_values=None,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Emergency contact soft deleted, contact_id: {contact_id}")

    except EmployeeEmergencyContactNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error deleting emergency contact {contact_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting emergency contact"
        )