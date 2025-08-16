from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.enums import Permission
from app.core.config import Settings, get_settings
from app.services.employee_emergency_contact_service import (
    create_emergency_contact as service_create_emergency_contact,
    get_emergency_contact as service_get_emergency_contact,
    list_emergency_contacts as service_list_emergency_contacts,
    update_emergency_contact as service_update_emergency_contact,
    delete_emergency_contact as service_delete_emergency_contact
)
from app.schemas.employee_emergency_contact import (
    EmployeeEmergencyContactCreate,
    EmployeeEmergencyContactUpdate,
    EmployeeEmergencyContactOut
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emergency-contacts", tags=["Employee Emergency Contacts"])

@router.post("/", 
             response_model=EmployeeEmergencyContactOut, 
             status_code=status.HTTP_201_CREATED,
             summary="Create emergency contact",
             description="Create emergency contact for an employee.")
@require_permissions([Permission.MANAGE_EMPLOYEES])
async def create_emergency_contact_endpoint(
    contact: EmployeeEmergencyContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> EmployeeEmergencyContactOut:
    """
    Create an emergency contact by delegating to employee_emergency_contact_service.
    """
    return await service_create_emergency_contact(contact, db, current_user, settings)

@router.get("/{contact_id}", 
            response_model=EmployeeEmergencyContactOut,
            summary="Get emergency contact by ID",
            description="Retrieve an emergency contact by ID, restricted to own contacts or with VIEW_ALL_ATTENDANCE permission.")
@require_permissions([Permission.VIEW_ALL_ATTENDANCE, Permission.VIEW_OWN_ATTENDANCE])
async def get_emergency_contact_endpoint(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> EmployeeEmergencyContactOut:
    """
    Retrieve an emergency contact by ID by delegating to employee_emergency_contact_service.
    """
    return await service_get_emergency_contact(contact_id, current_user, db, settings)

@router.get("/", 
            response_model=List[EmployeeEmergencyContactOut],
            summary="List emergency contacts",
            description="List emergency contacts, filtered by user_id for authorized users or own contacts.")
@require_permissions([Permission.VIEW_ALL_ATTENDANCE, Permission.VIEW_OWN_ATTENDANCE])
async def list_emergency_contacts_endpoint(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[EmployeeEmergencyContactOut]:
    """
    List emergency contacts by delegating to employee_emergency_contact_service.
    """
    return await service_list_emergency_contacts(user_id, skip, limit, current_user, db, settings)

@router.put("/{contact_id}", 
            response_model=EmployeeEmergencyContactOut,
            summary="Update emergency contact",
            description="Update an emergency contact, restricted to own contacts or with MANAGE_EMPLOYEES permission.")
@require_permissions([Permission.MANAGE_EMPLOYEES, Permission.VIEW_OWN_ATTENDANCE])
async def update_emergency_contact_endpoint(
    contact_id: int,
    contact_update: EmployeeEmergencyContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> EmployeeEmergencyContactOut:
    """
    Update an emergency contact by delegating to employee_emergency_contact_service.
    """
    return await service_update_emergency_contact(contact_id, contact_update, current_user, db, settings)

@router.delete("/{contact_id}", 
               status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete emergency contact",
               description="Soft delete an emergency contact.")
@require_permissions([Permission.MANAGE_EMPLOYEES])
async def delete_emergency_contact_endpoint(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> None:
    """
    Soft delete an emergency contact by delegating to employee_emergency_contact_service.
    """
    await service_delete_emergency_contact(contact_id, current_user, db, settings)