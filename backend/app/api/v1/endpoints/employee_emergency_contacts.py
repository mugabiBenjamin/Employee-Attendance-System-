from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, AsyncGenerator
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone
from app.core.database import AsyncSessionLocal
from app.models.employee_emergency_contacts import EmployeeEmergencyContacts
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.core.permissions import check_permissions
from app.core.security import get_current_active_user
from app.core.config import settings
from app.core.enums import Permission
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emergency-contacts", tags=["Employee Emergency Contacts"])

class EmergencyContactCreate(BaseModel):
    """Schema for creating a new emergency contact."""
    user_id: int
    contact_name: str
    relationship: str
    phone_number: str
    email: Optional[str] = None
    address: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class EmergencyContactUpdate(BaseModel):
    """Schema for updating an existing emergency contact."""
    contact_name: Optional[str] = None
    relationship: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class EmergencyContactOut(BaseModel):
    """Schema for emergency contact output."""
    contact_id: int
    user_id: int
    contact_name: str
    relationship: str
    phone_number: str
    email: Optional[str]
    address: Optional[str]
    created_at: datetime
    updated_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
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

async def is_admin_or_hr(db: AsyncSession, user: Users) -> bool:
    """Check if the user has HR, Admin, or Super_Admin role."""
    try:
        query = select(UserRoles).join(Roles).where(
            UserRoles.user_id == user.user_id,
            UserRoles.is_active == True,
            Roles.role_name.in_(["HR", "Admin", "Super_Admin"]),
            Roles.is_active == True
        )
        result = await db.execute(query)
        return result.scalar_one_or_none() is not None
    except Exception as e:
        logger.error(f"Error checking admin/hr role for user_id {user.user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error checking user role")

@router.post("/", response_model=EmergencyContactOut, status_code=status.HTTP_201_CREATED, summary="Create emergency contact", description="Create a new emergency contact for an employee. Requires manage_emergency_contacts permission or HR/admin access.")
async def create_emergency_contact(
    contact: EmergencyContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> EmergencyContactOut:
    """Create a new emergency contact for an employee."""
    try:
        has_permission = await check_permissions([Permission.MANAGE_EMERGENCY_CONTACTS.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create emergency contacts")

        # Verify user exists
        query = select(Users).where(
            Users.user_id == contact.user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        db_contact = EmployeeEmergencyContacts(
            **contact.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_contact)
        await db.commit()
        await db.refresh(db_contact)

        logger.info(f"Emergency contact created, contact_id: {db_contact.contact_id}, user_id: {db_contact.user_id}")
        return EmergencyContactOut.model_validate(db_contact)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating emergency contact: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating emergency contact")

@router.get("/{contact_id}", response_model=EmergencyContactOut, summary="Get emergency contact by ID", description="Retrieve emergency contact details. Requires view_emergency_contacts permission or HR/admin access.")
async def read_emergency_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> EmergencyContactOut:
    """Get a specific emergency contact by its ID."""
    try:
        has_permission = await check_permissions([Permission.VIEW_EMERGENCY_CONTACTS.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view emergency contacts")

        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active == True,
            EmployeeEmergencyContacts.deleted_at == None
        )
        result = await db.execute(query)
        contact = result.scalar_one_or_none()

        if not contact:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Emergency contact not found")

        logger.info(f"Retrieved emergency contact, contact_id: {contact_id}")
        return EmergencyContactOut.model_validate(contact)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving emergency contact {contact_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving emergency contact")

@router.get("/", response_model=List[EmergencyContactOut], summary="List emergency contacts", description="Retrieve all emergency contacts for a user or all users (HR/admin). Requires view_emergency_contacts permission or HR/admin access.")
async def read_emergency_contacts(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[EmergencyContactOut]:
    """Get a paginated list of emergency contacts, optionally filtered by user ID."""
    try:
        has_permission = await check_permissions([Permission.VIEW_EMERGENCY_CONTACTS.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view emergency contacts")

        if user_id and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view other users' emergency contacts")

        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.is_active == True,
            EmployeeEmergencyContacts.deleted_at == None
        )
        if user_id:
            query = query.where(EmployeeEmergencyContacts.user_id == user_id)
        elif not await is_admin_or_hr(db, current_user):
            query = query.where(EmployeeEmergencyContacts.user_id == current_user.user_id)
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        contacts = result.scalars().all()

        logger.info(f"Retrieved {len(contacts)} emergency contacts")
        return [EmergencyContactOut.model_validate(contact) for contact in contacts]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving emergency contacts: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving emergency contacts")

@router.put("/{contact_id}", response_model=EmergencyContactOut, summary="Update emergency contact", description="Update emergency contact information. Requires manage_emergency_contacts permission or HR/admin access.")
async def update_emergency_contact(
    contact_id: int,
    contact_update: EmergencyContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> EmergencyContactOut:
    """Update an existing emergency contact's information."""
    try:
        has_permission = await check_permissions([Permission.MANAGE_EMERGENCY_CONTACTS.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update emergency contacts")

        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active == True,
            EmployeeEmergencyContacts.deleted_at == None
        )
        result = await db.execute(query)
        contact = result.scalar_one_or_none()

        if not contact:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Emergency contact not found")

        if not await is_admin_or_hr(db, current_user) and contact.user_id != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this contact")

        update_data = contact_update.model_dump(exclude_none=True)
        for key, value in update_data.items():
            setattr(contact, key, value)

        contact.updated_at = datetime.now(timezone.utc)
        db.add(contact)
        await db.commit()
        await db.refresh(contact)

        logger.info(f"Emergency contact updated, contact_id: {contact_id}")
        return EmergencyContactOut.model_validate(contact)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating emergency contact {contact_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating emergency contact")

@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete emergency contact", description="Soft delete an emergency contact. Requires manage_emergency_contacts permission or HR/admin access.")
async def delete_emergency_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    """Soft delete an emergency contact from the system."""
    try:
        has_permission = await check_permissions([Permission.MANAGE_EMERGENCY_CONTACTS.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete emergency contacts")

        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active == True,
            EmployeeEmergencyContacts.deleted_at == None
        )
        result = await db.execute(query)
        contact = result.scalar_one_or_none()

        if not contact:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Emergency contact not found")

        if not await is_admin_or_hr(db, current_user) and contact.user_id != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this contact")

        contact.is_active = False
        contact.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Emergency contact soft deleted, contact_id: {contact_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting emergency contact {contact_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting emergency contact")