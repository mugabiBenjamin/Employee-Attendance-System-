from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime, timezone
from app.core.database import get_db
from app.models.employee_emergency_contacts import EmployeeEmergencyContacts
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.config import settings
from app.core.enums import Permission
from app.schemas.employee_emergency_contact import (
    EmployeeEmergencyContactCreate, 
    EmployeeEmergencyContactUpdate, 
    EmployeeEmergencyContactOut
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emergency-contacts", tags=["Employee Emergency Contacts"])

@router.post("/", response_model=EmployeeEmergencyContactOut, status_code=status.HTTP_201_CREATED)
@require_permissions([Permission.MANAGE_EMPLOYEES])
async def create_emergency_contact(
    contact: EmployeeEmergencyContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> EmployeeEmergencyContactOut:
    """Create emergency contact for an employee. Requires MANAGE_EMPLOYEES permission."""
    try:
        # Verify user exists and is active
        query = select(Users).where(
            Users.user_id == contact.user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        db_contact = EmployeeEmergencyContacts(
            user_id=contact.user_id,
            contact_name=contact.contact_name,
            relationship=contact.relationship,
            phone=contact.phone,
            email=contact.email,
            address=contact.address,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_contact)
        await db.commit()
        await db.refresh(db_contact)

        logger.info(f"Emergency contact created: {db_contact.contact_id} for user: {db_contact.user_id}")
        return EmployeeEmergencyContactOut.model_validate(db_contact)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating emergency contact: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating emergency contact")

@router.get("/{contact_id}", response_model=EmployeeEmergencyContactOut)
@require_permissions([Permission.VIEW_ALL_ATTENDANCE, Permission.VIEW_OWN_ATTENDANCE])
async def get_emergency_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> EmployeeEmergencyContactOut:
    """Get emergency contact by ID. Requires VIEW_ALL_ATTENDANCE for others' contacts or VIEW_OWN_ATTENDANCE for own contacts."""
    try:
        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active == True,
            EmployeeEmergencyContacts.deleted_at == None
        )
        result = await db.execute(query)
        contact = result.scalar_one_or_none()

        if not contact:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Emergency contact not found")

        # Check if user is viewing their own contact or has VIEW_ALL_ATTENDANCE
        if contact.user_id != current_user.user_id:
            await require_permissions([Permission.VIEW_ALL_ATTENDANCE])(get_emergency_contact)(contact_id=contact_id, db=db, current_user=current_user)

        return EmployeeEmergencyContactOut.model_validate(contact)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving emergency contact {contact_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving emergency contact")

@router.get("/", response_model=List[EmployeeEmergencyContactOut])
@require_permissions([Permission.VIEW_ALL_ATTENDANCE, Permission.VIEW_OWN_ATTENDANCE])
async def list_emergency_contacts(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[EmployeeEmergencyContactOut]:
    """List emergency contacts. Requires VIEW_ALL_ATTENDANCE for others' contacts or VIEW_OWN_ATTENDANCE for own contacts."""
    try:
        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.is_active == True,
            EmployeeEmergencyContacts.deleted_at == None
        )
        
        if user_id:
            # Only allow HR/Admin to filter by user_id
            await require_permissions([Permission.VIEW_ALL_ATTENDANCE])(list_emergency_contacts)(user_id=user_id, skip=skip, limit=limit, db=db, current_user=current_user)
            query = query.where(EmployeeEmergencyContacts.user_id == user_id)
        else:
            # Regular users see only their own contacts
            query = query.where(EmployeeEmergencyContacts.user_id == current_user.user_id)
        
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        contacts = result.scalars().all()

        return [EmployeeEmergencyContactOut.model_validate(contact) for contact in contacts]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving emergency contacts: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving emergency contacts")

@router.put("/{contact_id}", response_model=EmployeeEmergencyContactOut)
@require_permissions([Permission.MANAGE_EMPLOYEES, Permission.VIEW_OWN_ATTENDANCE])
async def update_emergency_contact(
    contact_id: int,
    contact_update: EmployeeEmergencyContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> EmployeeEmergencyContactOut:
    """Update emergency contact. Requires MANAGE_EMPLOYEES for others' contacts or VIEW_OWN_ATTENDANCE for own contacts."""
    try:
        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active == True,
            EmployeeEmergencyContacts.deleted_at == None
        )
        result = await db.execute(query)
        contact = result.scalar_one_or_none()

        if not contact:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Emergency contact not found")

        # Check if user is updating their own contact or has MANAGE_EMPLOYEES
        if contact.user_id != current_user.user_id:
            await require_permissions([Permission.MANAGE_EMPLOYEES])(update_emergency_contact)(contact_id=contact_id, contact_update=contact_update, db=db, current_user=current_user)

        # Apply updates
        update_data = contact_update.model_dump(exclude_none=True)
        for key, value in update_data.items():
            setattr(contact, key, value)

        contact.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(contact)

        logger.info(f"Emergency contact updated: {contact_id}")
        return EmployeeEmergencyContactOut.model_validate(contact)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating emergency contact {contact_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating emergency contact")

@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions([Permission.MANAGE_EMPLOYEES])
async def delete_emergency_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    """Soft delete emergency contact. Requires MANAGE_EMPLOYEES permission."""
    try:
        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active == True,
            EmployeeEmergencyContacts.deleted_at == None
        )
        result = await db.execute(query)
        contact = result.scalar_one_or_none()

        if not contact:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Emergency contact not found")

        contact.is_active = False
        contact.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Emergency contact deleted: {contact_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting emergency contact {contact_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting emergency contact")