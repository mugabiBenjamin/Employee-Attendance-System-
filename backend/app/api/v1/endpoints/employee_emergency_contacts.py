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
    description="Create an emergency contact for the current user."
)
@require_permissions([Permission.CREATE_EMERGENCY_CONTACT])
async def create_emergency_contact_endpoint(
    contact: EmployeeEmergencyContactCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> EmployeeEmergencyContactOut:
    """Create an emergency contact."""
    try:
        request_id = getattr(request.state, "request_id", None)
        return await create_emergency_contact(contact, request, current_user, db, settings, request_id)
    except Exception as e:
        logger.error(f"Error creating emergency contact for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise

@router.get(
    "/{contact_id}",
    response_model=EmployeeEmergencyContactOut,
    summary="Get emergency contact by ID",
    description="Retrieve an emergency contact by ID."
)
@require_permissions([Permission.VIEW_EMERGENCY_CONTACT, Permission.VIEW_OWN_EMERGENCY_CONTACT])
async def get_emergency_contact_endpoint(
    contact_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> EmployeeEmergencyContactOut:
    """Retrieve an emergency contact by ID."""
    try:
        request_id = getattr(request.state, "request_id", None)
        return await get_emergency_contact(contact_id, current_user, db, request_id)
    except Exception as e:
        logger.error(f"Error retrieving emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id})
        raise

@router.get(
    "/",
    response_model=List[EmployeeEmergencyContactOut],
    summary="List emergency contacts",
    description="Retrieve a list of emergency contacts, optionally filtered by user_id or department_id."
)
@require_permissions([Permission.VIEW_EMERGENCY_CONTACT, Permission.VIEW_OWN_EMERGENCY_CONTACT])
async def list_emergency_contacts_endpoint(
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    request: Request = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[EmployeeEmergencyContactOut]:
    """List emergency contacts with pagination."""
    try:
        request_id = getattr(request.state, "request_id", None)
        return await list_emergency_contacts(user_id, department_id, skip, limit, current_user, db, settings, request_id)
    except Exception as e:
        logger.error(f"Error retrieving emergency contacts for user_id {user_id or 'all'}: {str(e)}", extra={"request_id": request_id})
        raise

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
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> EmployeeEmergencyContactOut:
    """Update an emergency contact."""
    try:
        request_id = getattr(request.state, "request_id", None)
        return await update_emergency_contact(contact_id, contact_update, request, current_user, db, settings, request_id)
    except Exception as e:
        logger.error(f"Error updating emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id})
        raise

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
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> None:
    """Soft delete an emergency contact."""
    try:
        request_id = getattr(request.state, "request_id", None)
        await delete_emergency_contact(contact_id, request, current_user, db, settings, request_id)
    except Exception as e:
        logger.error(f"Error deleting emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id})
        raise