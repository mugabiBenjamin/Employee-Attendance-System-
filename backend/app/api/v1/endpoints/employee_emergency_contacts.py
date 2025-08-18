from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.employee_emergency_contact_service import (
    create_emergency_contact,
    get_emergency_contact,
    list_emergency_contacts,
    update_emergency_contact,
    delete_emergency_contact
)
from app.schemas.employee_emergency_contact import (
    EmployeeEmergencyContactCreate,
    EmployeeEmergencyContactUpdate,
    EmployeeEmergencyContactOut
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emergency-contacts", tags=["Employee Emergency Contacts"])

@router.post(
    "/",
    response_model=EmployeeEmergencyContactOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create emergency contact",
    description="Create an emergency contact for an employee."
)
@require_permissions([Permission.CREATE_EMERGENCY_CONTACT])
async def create_emergency_contact_endpoint(
    contact: EmployeeEmergencyContactCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> EmployeeEmergencyContactOut:
    """Create an emergency contact.

    Args:
        contact: Emergency contact creation data.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        EmployeeEmergencyContactOut: The created emergency contact.
    """
    return await create_emergency_contact(contact, request, current_user, db)

@router.get(
    "/{contact_id}",
    response_model=EmployeeEmergencyContactOut,
    summary="Get emergency contact by ID",
    description="Retrieve an emergency contact by ID."
)
@require_permissions([Permission.VIEW_EMERGENCY_CONTACT, Permission.VIEW_OWN_EMERGENCY_CONTACT])
async def get_emergency_contact_endpoint(
    contact_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> EmployeeEmergencyContactOut:
    """Retrieve an emergency contact by ID.

    Args:
        contact_id: The ID of the emergency contact to retrieve.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        EmployeeEmergencyContactOut: The retrieved emergency contact.
    """
    return await get_emergency_contact(contact_id, current_user, db)

@router.get(
    "/",
    response_model=List[EmployeeEmergencyContactOut],
    summary="List emergency contacts",
    description="Retrieve a list of emergency contacts, optionally filtered by user_id."
)
@require_permissions([Permission.VIEW_EMERGENCY_CONTACT, Permission.VIEW_OWN_EMERGENCY_CONTACT])
async def list_emergency_contacts_endpoint(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[EmployeeEmergencyContactOut]:
    """List emergency contacts with pagination.

    Args:
        user_id: Optional user ID to filter contacts.
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return.
        current_user: The authenticated user.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[EmployeeEmergencyContactOut]: List of emergency contacts.
    """
    return await list_emergency_contacts(user_id, skip, limit, current_user, db, settings)

@router.put(
    "/{contact_id}",
    response_model=EmployeeEmergencyContactOut,
    summary="Update emergency contact",
    description="Update an existing emergency contact."
)
@require_permissions([Permission.UPDATE_EMERGENCY_CONTACT, Permission.VIEW_OWN_EMERGENCY_CONTACT])
async def update_emergency_contact_endpoint(
    contact_id: int,
    contact_update: EmployeeEmergencyContactUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> EmployeeEmergencyContactOut:
    """Update an emergency contact.

    Args:
        contact_id: The ID of the emergency contact to update.
        contact_update: Emergency contact update data.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        EmployeeEmergencyContactOut: The updated emergency contact.
    """
    return await update_emergency_contact(contact_id, contact_update, request, current_user, db)

@router.delete(
    "/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete emergency contact",
    description="Soft delete an emergency contact."
)
@require_permissions([Permission.DELETE_EMERGENCY_CONTACT])
async def delete_emergency_contact_endpoint(
    contact_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> None:
    """Soft delete an emergency contact.

    Args:
        contact_id: The ID of the emergency contact to delete.
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.
    """
    await delete_emergency_contact(contact_id, request, current_user, db)