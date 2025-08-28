from fastapi import APIRouter, Depends, status, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.utils import get_request_id
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
from app.core.enums import Permission
from app.core.permissions import require_permissions_dependency, require_any_permissions_dependency
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
async def create_emergency_contact_endpoint(
    contact: EmployeeEmergencyContactCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _= Depends(require_permissions_dependency([Permission.CREATE_EMERGENCY_CONTACT]))
) -> EmployeeEmergencyContactOut:
    """Create an emergency contact for the current user."""
    request_id = None
    try:
        request_id = get_request_id(request)
        return await create_emergency_contact(contact, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error creating emergency contact for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating emergency contact for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error") from e

@router.get(
    "/{contact_id}",
    response_model=EmployeeEmergencyContactOut,
    summary="Get emergency contact by ID",
    description="Retrieve an emergency contact by ID."
)
async def get_emergency_contact_endpoint(
    contact_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _= Depends(require_any_permissions_dependency([Permission.VIEW_EMERGENCY_CONTACT, Permission.VIEW_OWN_EMERGENCY_CONTACT]))
) -> EmployeeEmergencyContactOut:
    """Retrieve an emergency contact by ID."""
    try:
        request_id = get_request_id(request)
        return await get_emergency_contact(contact_id, current_user, db, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/",
    response_model=List[EmployeeEmergencyContactOut],
    summary="List emergency contacts",
    description="Retrieve a list of emergency contacts, optionally filtered by user_id, department_id, or is_active status."
)
async def list_emergency_contacts_endpoint(
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    request: Request = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _= Depends(require_any_permissions_dependency([Permission.VIEW_EMERGENCY_CONTACT, Permission.VIEW_OWN_EMERGENCY_CONTACT]))
) -> List[EmployeeEmergencyContactOut]:
    """List emergency contacts with pagination and optional filters."""
    try:
        request_id = get_request_id(request)
        return await list_emergency_contacts(user_id, department_id, is_active, skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving emergency contacts for user_id {user_id or 'all'}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving emergency contacts for user_id {user_id or 'all'}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{contact_id}",
    response_model=EmployeeEmergencyContactOut,
    summary="Update emergency contact",
    description="Update an existing emergency contact."
)
async def update_emergency_contact_endpoint(
    contact_id: int,
    contact_update: EmployeeEmergencyContactUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _= Depends(require_any_permissions_dependency([Permission.UPDATE_EMERGENCY_CONTACT, Permission.VIEW_OWN_EMERGENCY_CONTACT]))
) -> EmployeeEmergencyContactOut:
    """Update an emergency contact."""
    try:
        request_id = get_request_id(request)
        return await update_emergency_contact(contact_id, contact_update, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error updating emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete emergency contact",
    description="Soft delete an emergency contact."
)
async def delete_emergency_contact_endpoint(
    contact_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _= Depends(require_permissions_dependency([Permission.DELETE_EMERGENCY_CONTACT]))
) -> None:
    """Soft delete an emergency contact."""
    try:
        request_id = get_request_id(request)
        await delete_emergency_contact(contact_id, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error deleting emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id, "user_id": current_user.user_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")