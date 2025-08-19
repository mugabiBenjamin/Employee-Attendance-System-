from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.employee_emergency_contacts import EmployeeEmergencyContacts
from app.models.users import Users
from app.schemas.employee_emergency_contact import EmployeeEmergencyContactCreate, EmployeeEmergencyContactUpdate, EmployeeEmergencyContactOut
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import UserNotFoundError, EmployeeEmergencyContactNotFoundError, ValidationError, DepartmentNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_user_exists
from app.services.system_log_service import create_system_log
from app.schemas.system_log import SystemLogCreate
import logging

logger = logging.getLogger(__name__)

async def create_emergency_contact(
    contact: EmployeeEmergencyContactCreate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.CREATE_EMERGENCY_CONTACT]))
) -> EmployeeEmergencyContactOut:
    """Create a new emergency contact for the current user with validation, logging, and cache clearing."""
    try:
        # Validate current user
        await validate_user_exists(db, current_user.user_id, request_id)

        # Validate phone numbers
        if contact.alternate_phone and contact.alternate_phone == contact.phone:
            raise ValidationError(detail="Alternate phone must be different from primary phone")

        db_contact = EmployeeEmergencyContacts(
            user_id=current_user.user_id,
            **contact.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_contact)
        await db.commit()
        await db.refresh(db_contact)

        # Invalidate cache
        await invalidate_cache_prefix("emergency_contact")
        await invalidate_cache_prefix(f"user:{current_user.user_id}")
        logger.debug(f"Cache cleared for emergency_contact and user:{current_user.user_id}")

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.CREATE_EMERGENCY_CONTACT,
            table_affected="employee_emergency_contacts",
            record_id=db_contact.contact_id,
            old_values=None,
            new_values=db_contact.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Emergency contact created, contact_id: {db_contact.contact_id}, user_id: {current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return EmployeeEmergencyContactOut.model_validate(db_contact)

    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating emergency contact for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating emergency contact")

async def get_emergency_contact(
    contact_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_EMERGENCY_CONTACT, Permission.VIEW_OWN_EMERGENCY_CONTACT]))
) -> EmployeeEmergencyContactOut:
    """Retrieve an emergency contact by ID."""
    try:
        cache_key = f"emergency_contact:{contact_id}"
        cached_contact = await get_cache(cache_key)
        if cached_contact:
            return EmployeeEmergencyContactOut(**cached_contact)

        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active == True,
            EmployeeEmergencyContacts.deleted_at == None
        )
        result = await db.execute(query)
        contact = result.scalar_one_or_none()

        if not contact:
            raise EmployeeEmergencyContactNotFoundError(contact_id=contact_id)

        if contact.user_id != current_user.user_id and not any(p in current_user.permissions for p in [Permission.VIEW_EMERGENCY_CONTACT, Permission.MANAGE_EMPLOYEES]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this emergency contact"
            )

        contact_dict = EmployeeEmergencyContactOut.model_validate(contact).model_dump()
        await set_cache(cache_key, contact_dict, ttl=300)

        logger.info(
            f"Retrieved emergency contact: contact_id={contact_id}",
            extra={"request_id": request_id}
        )
        return EmployeeEmergencyContactOut.model_validate(contact)

    except EmployeeEmergencyContactNotFoundError as e:
        logger.error(f"Emergency contact not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Error retrieving emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving emergency contact")

async def list_emergency_contacts(
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_EMERGENCY_CONTACT, Permission.VIEW_OWN_EMERGENCY_CONTACT]))
) -> List[EmployeeEmergencyContactOut]:
    """Retrieve a list of emergency contacts for an employee or department with pagination."""
    try:
        if skip < 0 or (limit is not None and limit < 0):
            raise ValidationError(detail="Invalid pagination parameters")

        limit = limit or settings.DEFAULT_PAGE_SIZE
        target_user_id = user_id if user_id else current_user.user_id if not department_id else None

        if target_user_id and target_user_id != current_user.user_id and not any(p in current_user.permissions for p in [Permission.VIEW_EMERGENCY_CONTACT, Permission.MANAGE_EMPLOYEES]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view other user's emergency contacts")

        cache_key = f"emergency_contacts:{target_user_id or 'all'}:{department_id or 'all'}:{skip}:{limit}"
        cached_contacts = await get_cache(cache_key)
        if cached_contacts:
            return [EmployeeEmergencyContactOut(**c) for c in cached_contacts]

        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.is_active == True,
            EmployeeEmergencyContacts.deleted_at == None
        )

        if department_id:
            from app.models.user_departments import UserDepartments
            from app.core.validators import validate_department_exists
            await validate_department_exists(db, department_id, request_id)
            query = query.join(UserDepartments, UserDepartments.user_id == EmployeeEmergencyContacts.user_id).where(
                UserDepartments.department_id == department_id,
                UserDepartments.is_active == True,
                UserDepartments.deleted_at == None
            )
        elif target_user_id:
            await validate_user_exists(db, target_user_id, request_id)
            query = query.where(EmployeeEmergencyContacts.user_id == target_user_id)

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        contacts = result.scalars().all()

        contacts_dict = [EmployeeEmergencyContactOut.model_validate(c).model_dump() for c in contacts]
        await set_cache(cache_key, contacts_dict, ttl=300)

        logger.info(
            f"Retrieved {len(contacts)} emergency contacts for user_id: {target_user_id or 'all'}, department_id: {department_id or 'all'}",
            extra={"request_id": request_id}
        )
        return [EmployeeEmergencyContactOut.model_validate(contact) for contact in contacts]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (UserNotFoundError, DepartmentNotFoundError) as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Error retrieving emergency contacts: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving emergency contacts")

async def update_emergency_contact(
    contact_id: int,
    contact_update: EmployeeEmergencyContactUpdate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.UPDATE_EMERGENCY_CONTACT, Permission.VIEW_OWN_EMERGENCY_CONTACT]))
) -> EmployeeEmergencyContactOut:
    """Update an emergency contact with validation, logging, and cache clearing."""
    try:
        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active == True,
            EmployeeEmergencyContacts.deleted_at == None
        )
        result = await db.execute(query)
        db_contact = result.scalar_one_or_none()

        if not db_contact:
            raise EmployeeEmergencyContactNotFoundError(contact_id=contact_id)

        if db_contact.user_id != current_user.user_id and not any(p in current_user.permissions for p in [Permission.UPDATE_EMERGENCY_CONTACT, Permission.MANAGE_EMPLOYEES]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this emergency contact"
            )

        update_data = contact_update.model_dump(exclude_none=True)
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        if update_data.get('alternate_phone') and update_data.get('phone', db_contact.phone) == update_data['alternate_phone']:
            raise ValidationError(detail="Alternate phone must be different from primary phone")

        old_values = db_contact.__dict__.copy()
        for key, value in update_data.items():
            setattr(db_contact, key, value)

        db_contact.updated_at = datetime.now(timezone.utc)
        db.add(db_contact)
        await db.commit()
        await db.refresh(db_contact)

        # Invalidate cache
        await invalidate_cache_prefix("emergency_contact")
        await invalidate_cache_prefix(f"user:{db_contact.user_id}")
        logger.debug(f"Cache cleared for emergency_contact and user:{db_contact.user_id}")

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE_EMERGENCY_CONTACT,
            table_affected="employee_emergency_contacts",
            record_id=contact_id,
            old_values=old_values,
            new_values=db_contact.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Emergency contact updated, contact_id: {contact_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return EmployeeEmergencyContactOut.model_validate(db_contact)

    except EmployeeEmergencyContactNotFoundError as e:
        logger.error(f"Emergency contact not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Error updating emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating emergency contact")

async def delete_emergency_contact(
    contact_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.DELETE_EMERGENCY_CONTACT]))
) -> None:
    """Soft delete an emergency contact with logging and cache clearing."""
    try:
        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active == True,
            EmployeeEmergencyContacts.deleted_at == None
        )
        result = await db.execute(query)
        db_contact = result.scalar_one_or_none()

        if not db_contact:
            raise EmployeeEmergencyContactNotFoundError(contact_id=contact_id)

        if not any(p in current_user.permissions for p in [Permission.DELETE_EMERGENCY_CONTACT, Permission.MANAGE_EMPLOYEES]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this emergency contact"
            )

        old_values = db_contact.__dict__.copy()
        db_contact.is_active = False
        db_contact.deleted_at = datetime.now(timezone.utc)
        db_contact.updated_at = datetime.now(timezone.utc)
        db.add(db_contact)
        await db.commit()

        # Invalidate cache
        await invalidate_cache_prefix("emergency_contact")
        await invalidate_cache_prefix(f"user:{db_contact.user_id}")
        logger.debug(f"Cache cleared for emergency_contact and user:{db_contact.user_id}")

        # Log the action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE_EMERGENCY_CONTACT,
            table_affected="employee_emergency_contacts",
            record_id=contact_id,
            old_values=old_values,
            new_values=None,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"Emergency contact soft deleted, contact_id: {contact_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except EmployeeEmergencyContactNotFoundError as e:
        logger.error(f"Emergency contact not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Error deleting emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting emergency contact")