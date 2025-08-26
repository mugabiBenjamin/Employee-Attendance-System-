from typing import List, Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.users import Users
from app.schemas.user import UserCreate, UserUpdate, UserOut
from app.core.security import get_password_hash
from app.core.enums import SystemAction, Permission, EmployeeType
from app.core.exceptions import ValidationError, DatabaseError, UserNotFoundError, ResourceConflictError, BusinessLogicError
from app.core.security import get_current_user
from app.core.permissions import require_permissions, invalidate_user_cache
from app.services.system_log_service import create_system_log
from app.schemas.system_log import SystemLogCreate
from app.core.validators import validate_user_exists
from app.core.config import Settings, get_settings
from app.core.database import get_db, get_cache, set_cache, invalidate_cache_prefix, validate_enum_value
import logging

logger = logging.getLogger(__name__)

async def create_user(
    user: UserCreate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.CREATE_USER]))
) -> UserOut:
    """Create a new user with validation and logging."""
    try:
        # Validate employee_type
        if user.employee_type and not await validate_enum_value(EmployeeType, user.employee_type):
            raise ValidationError(detail=f"Invalid employee type: {user.employee_type}")

        # Check for existing email
        query = select(Users).where(
            Users.email == user.email,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ResourceConflictError(detail="Email already registered")

        # Validate supervisor_id if provided
        if user.supervisor_id:
            await validate_user_exists(user.supervisor_id, db)

        # Validate required fields
        if not user.email or not user.password:
            raise ValidationError(detail="Email and password are required")

        hashed_password = get_password_hash(user.password)
        db_user = Users(
            email=user.email,
            password_hash=hashed_password,
            first_name=user.first_name,
            last_name=user.last_name,
            phone=user.phone,
            job_title=user.job_title,
            hire_date=user.hire_date,
            employee_type=user.employee_type,
            salary=user.salary,
            supervisor_id=user.supervisor_id,
            is_active=user.is_active,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)

        # Invalidate cache for users list and user
        await invalidate_cache_prefix("users")
        invalidate_user_cache(db_user.user_id)
        logger.info(f"Cache invalidated for user_id: {db_user.user_id} and users list")

        # Log action using SystemAction.INSERT
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="users",
            record_id=db_user.user_id,
            old_values=None,
            new_values=db_user.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"User created, user_id: {db_user.user_id}, email: {db_user.email}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return UserOut.model_validate(db_user)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ResourceConflictError as e:
        logger.error(f"Resource conflict: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error creating user: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error creating user: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def read_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_USER]))
) -> UserOut:
    """Retrieve a user by ID."""
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user ID")

        cache_key = f"user:{user_id}"
        cached_user = await get_cache(cache_key)
        if cached_user:
            logger.info(f"Cache hit for user_id: {user_id}", extra={"request_id": request_id})
            return UserOut(**cached_user)

        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(user_id=user_id)

        user_dict = UserOut.model_validate(user).model_dump()
        await set_cache(cache_key, user_dict, ttl=300)
        logger.info(f"Cache set for user_id inaccurately {user_id}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved user, user_id: {user_id}",
            extra={"request_id": request_id}
        )
        return UserOut.model_validate(user)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def read_users(
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_USER]))
) -> List[UserOut]:
    """Retrieve a list of active users with pagination."""
    try:
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")

        limit = limit or settings.DEFAULT_PAGE_SIZE
        cache_key = f"users:{skip}:{limit}"
        cached_users = await get_cache(cache_key)
        if cached_users:
            logger.info(f"Cache hit for users list, skip: {skip}, limit: {limit}", extra={"request_id": request_id})
            return [UserOut(**user) for user in cached_users]

        query = select(Users).where(
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        users = result.scalars().all()

        users_dict = [UserOut.model_validate(user).model_dump() for user in users]
        await set_cache(cache_key, users_dict, ttl=300)
        logger.info(f"Cache set for users list, skip: {skip}, limit: {limit}", extra={"request_id": request_id})

        logger.info(
            f"Retrieved {len(users)} users",
            extra={"request_id": request_id}
        )
        return [UserOut.model_validate(user) for user in users]

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving users: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving users: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def update_user(
    user_id: int,
    user_update: UserUpdate,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.UPDATE_USER]))
) -> UserOut:
    """Update a user with validation and logging."""
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user ID")

        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_user = result.scalar_one_or_none()

        if not db_user:
            raise UserNotFoundError(user_id=user_id)

        update_data = user_update.model_dump(exclude_none=True)
        if not update_data:
            raise ValidationError(detail="No fields provided for update")

        if "email" in update_data:
            query = select(Users).where(
                Users.email == update_data["email"],
                Users.user_id != user_id,
                Users.is_active.is_(True),
                Users.deleted_at.is_(None)
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise ResourceConflictError(detail="Email already registered")

        if "supervisor_id" in update_data and update_data["supervisor_id"] is not None:
            await validate_user_exists(update_data["supervisor_id"], db)

        if "employee_type" in update_data and update_data["employee_type"]:
            if not await validate_enum_value(EmployeeType, update_data["employee_type"]):
                raise ValidationError(detail=f"Invalid employee type: {update_data['employee_type']}")

        old_values = db_user.__dict__.copy()

        for key, value in update_data.items():
            if key == "password" and value:
                value = get_password_hash(value)
                setattr(db_user, "password_hash", value)
            else:
                setattr(db_user, key, value)

        db_user.updated_at = datetime.now(timezone.utc)
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)

        # Invalidate cache for user and users list
        await invalidate_cache_prefix("users")
        invalidate_user_cache(user_id)
        logger.info(f"Cache invalidated for user_id: {user_id} and users list")

        # Log action using SystemAction.UPDATE
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE,
            table_affected="users",
            record_id=user_id,
            old_values=old_values,
            new_values=db_user.__dict__,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"User updated, user_id: {user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )
        return UserOut.model_validate(db_user)

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ResourceConflictError as e:
        logger.error(f"Resource conflict: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error updating user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error updating user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def delete_user(
    user_id: int,
    request: Optional[Request] = None,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.DELETE_USER]))
) -> None:
    """Soft delete a user with validation and logging."""
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user ID")

        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        db_user = result.scalar_one_or_none()

        if not db_user:
            raise UserNotFoundError(user_id=user_id)

        query = select(Users).where(
            Users.supervisor_id == user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        if result.scalars().all():
            raise BusinessLogicError(detail="Cannot delete user with active subordinates")

        db_user.is_active = False
        db_user.deleted_at = datetime.now(timezone.utc)
        db.add(db_user)
        await db.commit()

        # Invalidate cache for user and users list
        await invalidate_cache_prefix("users")
        invalidate_user_cache(user_id)
        logger.info(f"Cache invalidated for user_id: {user_id} and users list")

        # Log action using SystemAction.DELETE
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE,
            table_affected="users",
            record_id=user_id,
            old_values=db_user.__dict__,
            new_values=None,
            ip_address=str(request.client.host) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            request_id=request_id
        )
        await create_system_log(log, request, current_user, db, request_id)

        logger.info(
            f"User soft deleted, user_id: {user_id}",
            extra={"request_id": request_id, "user_id": current_user.user_id}
        )

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BusinessLogicError as e:
        logger.error(f"Business logic error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error deleting user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error deleting user {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

async def get_current_user_profile(
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = None,
    _: bool = Depends(require_permissions([Permission.VIEW_OWN_PROFILE]))
) -> UserOut:
    """Retrieve the current authenticated user's profile."""
    try:
        query = select(Users).where(
            Users.user_id == current_user.user_id,
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(user_id=current_user.user_id)

        logger.info(
            f"Retrieved profile for user_id: {current_user.user_id}",
            extra={"request_id": request_id}
        )
        return UserOut.model_validate(user)

    except UserNotFoundError as e:
        logger.error(f"User not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error retrieving profile for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error retrieving profile for user_id {current_user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")