from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select, and_
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.models.employee_emergency_contacts import EmployeeEmergencyContacts
from app.models.users import Users
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.user_departments import UserDepartments
from app.schemas.employee_emergency_contact import EmployeeEmergencyContactCreate, EmployeeEmergencyContactUpdate, EmployeeEmergencyContactOut
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import UserNotFoundError, EmployeeEmergencyContactNotFoundError, ValidationError, DepartmentNotFoundError
from app.core.security import get_current_user
from app.core.permissions import require_permissions, invalidate_user_cache, get_user_permissions
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix
from app.core.validators import validate_user_exists, validate_department_exists
from app.core.utils import get_request_id, get_users_with_permission
from app.services.system_log_service import create_system_log
from app.schemas.system_log import SystemLogCreate
from app.core.mail import send_email
import logging
import re

logger = logging.getLogger(__name__)

def validate_phone_number(phone: str) -> bool:
    """Validate phone number format (E.164, e.g., +254712345678)."""
    pattern = r"^\+\d{1,3}\d{9,15}$"
    return bool(re.match(pattern, phone))

async def create_emergency_contact(
    contact: EmployeeEmergencyContactCreate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.CREATE_EMERGENCY_CONTACT]))
) -> EmployeeEmergencyContactOut:
    """Create a new emergency contact for the current user with validation, logging, and cache clearing."""
    try:
        # Validate current user
        await validate_user_exists(db, current_user.user_id, request_id)

        # Validate phone numbers
        if not validate_phone_number(contact.phone):
            raise ValidationError(detail="Invalid phone number format (use E.164, e.g., +254712345678)")
        if contact.alternate_phone and not validate_phone_number(contact.alternate_phone):
            raise ValidationError(detail="Invalid alternate phone number format (use E.164, e.g., +254712345678)")
        if contact.alternate_phone and contact.alternate_phone == contact.phone:
            raise ValidationError(detail="Alternate phone must be different from primary phone")

        # Check for duplicate phone numbers for the user
        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.user_id == current_user.user_id,
            EmployeeEmergencyContacts.is_active.is_(True),
            EmployeeEmergencyContacts.deleted_at.is_(None),
            or_(
                EmployeeEmergencyContacts.phone == contact.phone,
                EmployeeEmergencyContacts.phone == contact.alternate_phone,
                EmployeeEmergencyContacts.alternate_phone == contact.phone,
                EmployeeEmergencyContacts.alternate_phone == contact.alternate_phone
            )
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ValidationError(detail="Phone number already used for another emergency contact")

        # Check maximum emergency contacts limit
        query_count = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.user_id == current_user.user_id,
            EmployeeEmergencyContacts.is_active.is_(True),
            EmployeeEmergencyContacts.deleted_at.is_(None)
        )
        result_count = await db.execute(query_count)
        if len(result_count.scalars().all()) >= settings.MAX_EMERGENCY_CONTACTS:
            raise ValidationError(detail=f"Maximum emergency contacts ({settings.MAX_EMERGENCY_CONTACTS}) reached")

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
        invalidate_user_cache(current_user.user_id)
        await invalidate_cache_prefix("emergency_contact")
        await invalidate_cache_prefix(f"user:{current_user.user_id}")
        logger.info(f"Cache invalidated for emergency_contact and user:{current_user.user_id}", extra={"request_id": request_id})

        # Notify admins
        await _notify_admins_of_contact_change(db, db_contact, current_user, request_id, settings, "created")

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
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Emergency contact created, contact_id: {db_contact.contact_id}, user_id: {current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return EmployeeEmergencyContactOut.model_validate(db_contact)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating emergency contact for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating emergency contact")

async def get_emergency_contact(
    contact_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_EMERGENCY_CONTACT, Permission.VIEW_OWN_EMERGENCY_CONTACT]))
) -> EmployeeEmergencyContactOut:
    """Retrieve an emergency contact by ID with authorization check."""
    try:
        if contact_id <= 0:
            raise ValidationError(detail="Invalid contact_id")

        cache_key = f"emergency_contact:{contact_id}"
        cached_contact = await get_cache(cache_key)
        if cached_contact:
            logger.info(f"Cache hit for emergency_contact:{contact_id}", extra={"request_id": request_id})
            return EmployeeEmergencyContactOut(**cached_contact)

        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active.is_(True),
            EmployeeEmergencyContacts.deleted_at.is_(None)
        )
        result = await db.execute(query)
        contact = result.scalar_one_or_none()

        if not contact:
            raise EmployeeEmergencyContactNotFoundError(contact_id=contact_id)

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if contact.user_id != current_user.user_id:
            query_hierarchy = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == contact.user_id,
                EmployeeHierarchy.supervisor_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result_hierarchy = await db.execute(query_hierarchy)
            if not result_hierarchy.scalar_one_or_none() and not any(p == Permission.VIEW_EMERGENCY_CONTACT.value or p == Permission.MANAGE_EMPLOYEES.value for p in user_permissions):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view this emergency contact"
                )

        contact_dict = EmployeeEmergencyContactOut.model_validate(contact).model_dump()
        await set_cache(cache_key, contact_dict, ttl=300)
        logger.info(f"Cache set for emergency_contact:{contact_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved emergency contact: contact_id={contact_id}, user_id={current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return EmployeeEmergencyContactOut.model_validate(contact)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except EmployeeEmergencyContactNotFoundError as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error retrieving emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving emergency contact")

async def list_emergency_contacts(
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.VIEW_EMERGENCY_CONTACT, Permission.VIEW_OWN_EMERGENCY_CONTACT]))
) -> List[EmployeeEmergencyContactOut]:
    """Retrieve a list of emergency contacts for an employee or department with pagination."""
    try:
        if user_id and department_id:
            raise ValidationError(detail="Cannot specify both user_id and department_id")
        if skip < 0 or (limit is not None and limit < 0):
            raise ValidationError(detail="Invalid pagination parameters")

        limit = limit or settings.DEFAULT_PAGE_SIZE
        target_user_id = user_id if user_id else current_user.user_id if not department_id else None

        user_permissions = await get_user_permissions(current_user.user_id, db)
        if target_user_id and target_user_id != current_user.user_id:
            query_hierarchy = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == target_user_id,
                EmployeeHierarchy.supervisor_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result_hierarchy = await db.execute(query_hierarchy)
            if not result_hierarchy.scalar_one_or_none() and not any(p == Permission.VIEW_EMERGENCY_CONTACT.value or p == Permission.MANAGE_EMPLOYEES.value for p in user_permissions):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view other user's emergency contacts"
                )

        cache_key = f"emergency_contacts:{target_user_id or 'all'}:{department_id or 'all'}:{is_active or 'all'}:{skip}:{limit}"
        cached_contacts = await get_cache(cache_key)
        if cached_contacts:
            logger.info(f"Cache hit for emergency_contacts:{target_user_id or 'all'}:{department_id or 'all'}:{is_active or 'all'}:{skip}:{limit}", extra={"request_id": request_id})
            return [EmployeeEmergencyContactOut(**c) for c in cached_contacts]

        query = select(EmployeeEmergencyContacts)
        if is_active is not None:
            query = query.where(EmployeeEmergencyContacts.is_active.is_(is_active))
        else:
            query = query.where(EmployeeEmergencyContacts.is_active.is_(True), EmployeeEmergencyContacts.deleted_at.is_(None))

        if department_id:
            await validate_department_exists(db, department_id, request_id)
            query = query.join(
                UserDepartments,
                and_(
                    UserDepartments.user_id == EmployeeEmergencyContacts.user_id,
                    UserDepartments.department_id == department_id,
                    UserDepartments.is_active.is_(True),
                    UserDepartments.deleted_at.is_(None)
                )
            )
        elif target_user_id:
            if target_user_id <= 0:
                raise ValidationError(detail="Invalid user_id")
            await validate_user_exists(db, target_user_id, request_id)
            query = query.where(EmployeeEmergencyContacts.user_id == target_user_id)

        query = query.order_by(EmployeeEmergencyContacts.contact_id.asc()).offset(skip).limit(limit)
        result = await db.execute(query)
        contacts = result.scalars().all()

        contacts_dict = [EmployeeEmergencyContactOut.model_validate(c).model_dump() for c in contacts]
        await set_cache(cache_key, contacts_dict, ttl=300)
        logger.info(f"Cache set for emergency_contacts:{target_user_id or 'all'}:{department_id or 'all'}:{is_active or 'all'}:{skip}:{limit}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(contacts)} emergency contacts for user_id: {target_user_id or 'all'}, department_id: {department_id or 'all'}, is_active: {is_active or 'all'}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return [EmployeeEmergencyContactOut.model_validate(contact) for contact in contacts]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (UserNotFoundError, DepartmentNotFoundError) as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error retrieving emergency contacts: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving emergency contacts: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving emergency contacts")

async def update_emergency_contact(
    contact_id: int,
    contact_update: EmployeeEmergencyContactUpdate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.UPDATE_EMERGENCY_CONTACT, Permission.VIEW_OWN_EMERGENCY_CONTACT]))
) -> EmployeeEmergencyContactOut:
    """Update an emergency contact with validation, logging, and cache clearing."""
    try:
        if contact_id <= 0:
            raise ValidationError(detail="Invalid contact_id")

        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active.is_(True),
            EmployeeEmergencyContacts.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_contact = result.scalar_one_or_none()

        if not db_contact:
            raise EmployeeEmergencyContactNotFoundError(contact_id=contact_id)

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if db_contact.user_id != current_user.user_id:
            query_hierarchy = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == db_contact.user_id,
                EmployeeHierarchy.supervisor_id == current_user.user_id,
                EmployeeHierarchy.is_active.is_(True),
                EmployeeHierarchy.deleted_at.is_(None)
            )
            result_hierarchy = await db.execute(query_hierarchy)
            if not result_hierarchy.scalar_one_or_none() and not any(p == Permission.UPDATE_EMERGENCY_CONTACT.value or p == Permission.MANAGE_EMPLOYEES.value for p in user_permissions):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to update this emergency contact"
                )

        update_data = contact_update.model_dump(exclude_none=True)
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        # Validate phone numbers
        phone = update_data.get('phone', db_contact.phone)
        alternate_phone = update_data.get('alternate_phone', db_contact.alternate_phone)
        if phone and not validate_phone_number(phone):
            raise ValidationError(detail="Invalid phone number format (use E.164, e.g., +254712345678)")
        if alternate_phone and not validate_phone_number(alternate_phone):
            raise ValidationError(detail="Invalid alternate phone number format (use E.164, e.g., +254712345678)")
        if alternate_phone and phone == alternate_phone:
            raise ValidationError(detail="Alternate phone must be different from primary phone")

        # Check for duplicate phone numbers
        if 'phone' in update_data or 'alternate_phone' in update_data:
            query = select(EmployeeEmergencyContacts).where(
                EmployeeEmergencyContacts.user_id == db_contact.user_id,
                EmployeeEmergencyContacts.contact_id != contact_id,
                EmployeeEmergencyContacts.is_active.is_(True),
                EmployeeEmergencyContacts.deleted_at.is_(None),
                or_(
                    EmployeeEmergencyContacts.phone == phone,
                    EmployeeEmergencyContacts.phone == alternate_phone,
                    EmployeeEmergencyContacts.alternate_phone == phone,
                    EmployeeEmergencyContacts.alternate_phone == alternate_phone
                )
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise ValidationError(detail="Phone number already used for another emergency contact")

        old_values = db_contact.__dict__.copy()
        for key, value in update_data.items():
            setattr(db_contact, key, value)

        db_contact.updated_at = datetime.now(timezone.utc)
        db.add(db_contact)
        await db.commit()
        await db.refresh(db_contact)

        # Invalidate cache
        invalidate_user_cache(db_contact.user_id)
        await invalidate_cache_prefix("emergency_contact")
        await invalidate_cache_prefix(f"user:{db_contact.user_id}")
        logger.info(f"Cache invalidated for emergency_contact and user:{db_contact.user_id}", extra={"request_id": request_id})

        # Notify admins
        await _notify_admins_of_contact_change(db, db_contact, current_user, request_id, settings, "updated")

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
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Emergency contact updated, contact_id: {contact_id}, user_id: {current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return EmployeeEmergencyContactOut.model_validate(db_contact)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except EmployeeEmergencyContactNotFoundError as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error updating emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating emergency contact")

async def delete_emergency_contact(
    contact_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id),
    _: bool = Depends(require_permissions([Permission.DELETE_EMERGENCY_CONTACT]))
) -> None:
    """Soft delete an emergency contact with logging and cache clearing."""
    try:
        if contact_id <= 0:
            raise ValidationError(detail="Invalid contact_id")

        query = select(EmployeeEmergencyContacts).where(
            EmployeeEmergencyContacts.contact_id == contact_id,
            EmployeeEmergencyContacts.is_active.is_(True),
            EmployeeEmergencyContacts.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_contact = result.scalar_one_or_none()

        if not db_contact:
            raise EmployeeEmergencyContactNotFoundError(contact_id=contact_id)

        # Authorization check
        user_permissions = await get_user_permissions(current_user.user_id, db)
        if not any(p == Permission.DELETE_EMERGENCY_CONTACT.value or p == Permission.MANAGE_EMPLOYEES.value for p in user_permissions):
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
        invalidate_user_cache(db_contact.user_id)
        await invalidate_cache_prefix("emergency_contact")
        await invalidate_cache_prefix(f"user:{db_contact.user_id}")
        logger.info(f"Cache invalidated for emergency_contact and user:{db_contact.user_id}", extra={"request_id": request_id})

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
        await create_system_log(log, request, current_user, db, settings, request_id)

        logger.info(
            f"Emergency contact soft deleted, contact_id: {contact_id}, user_id: {current_user.user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except EmployeeEmergencyContactNotFoundError as e:
        logger.error(f"Not found error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException as e:
        logger.error(f"Authorization error deleting emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting emergency contact {contact_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting emergency contact")

async def _notify_admins_of_contact_change(
    db: AsyncSession,
    contact: EmployeeEmergencyContacts,
    current_user: Users,
    request_id: Optional[str],
    settings: Settings,
    action: str
) -> None:
    """Send notification email to admins about emergency contact creation or update."""
    try:
        eat_tz = ZoneInfo("Africa/Nairobi")
        current_time_eat = datetime.now(timezone.utc).astimezone(eat_tz)
        admins = await get_users_with_permission(Permission.MANAGE_EMPLOYEES, db)
        recipients = [(admin.email, admin.first_name) for admin in admins if admin.email]

        for email, first_name in recipients:
            await send_email(
                to_email=email,
                subject=f"Emergency Contact {action.title()} (ID: {contact.contact_id})",
                body=(
                    f"Dear {first_name},\n\n"
                    f"An emergency contact has been {action} for {current_user.first_name} {current_user.last_name} ({current_user.email}).\n\n"
                    f"Details:\n"
                    f"Contact ID: {contact.contact_id}\n"
                    f"Name: {contact.contact_name}\n"
                    f"Relationship: {contact.relationship}\n"
                    f"Phone: {contact.phone}\n"
                    f"Alternate Phone: {contact.alternate_phone or 'N/A'}\n"
                    f"{action.title()} At: {current_time_eat.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                    f"Please review in the Employee Management System.\n\n"
                    f"Best regards,\nEmployee Management System"
                ),
                request_id=request_id
            )
        logger.info(
            f"Sent notifications to {len(recipients)} admins for emergency contact {action}, contact_id={contact.contact_id}",
            extra={"request_id": request_id}
        )
    except Exception as e:
        logger.error(
            f"Failed to send notifications for emergency contact {action}, contact_id={contact.contact_id}: {str(e)}",
            extra={"request_id": request_id}
        )