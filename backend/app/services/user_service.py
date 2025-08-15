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
from app.core.permissions import require_permissions
from app.services.system_log_service import SystemLogService, get_system_log_service
from app.schemas.system_log import SystemLogCreate
from app.core.validators import validate_user_exists
from app.core.config import Settings, get_settings
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

async def create_user(
    user: UserCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    log_service: SystemLogService = Depends(get_system_log_service),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.CREATE_USER]))
) -> UserOut:
    """
    Create a new user with validation and logging. Requires CREATE_USER permission.
    """
    try:
        # Validate employee_type
        if user.employee_type not in [e.value for e in EmployeeType]:
            raise ValidationError(detail=f"Invalid employee_type. Must be one of: {[e.value for e in EmployeeType]}")

        # Check for existing email
        query = select(Users).where(
            Users.email == user.email,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ResourceConflictError(detail="Email already registered")

        # Validate manager_id if provided
        if user.manager_id:
            await validate_user_exists(db, user.manager_id)

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
            manager_id=user.manager_id,
            is_active=user.is_active,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="users",
            record_id=db_user.user_id,
            old_values=None,
            new_values=db_user.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent")
        )
        await log_service.create_system_log(log, current_user, request)

        logger.info(f"User created, user_id: {db_user.user_id}, email: {db_user.email}")
        return UserOut.model_validate(db_user)

    except ValidationError as e:
        logger.error(f"Validation error in create_user: {str(e)}")
        raise
    except ResourceConflictError as e:
        logger.error(f"Conflict error in create_user: {str(e)}")
        raise
    except DatabaseError as e:
        logger.error(f"Database error in create_user: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in create_user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error creating user"
        )

async def get_user_by_id(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_USER]))
) -> Optional[UserOut]:
    """
    Retrieve a user by ID. Requires VIEW_USER permission.
    """
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user ID")

        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(user_id=user_id)

        return UserOut.model_validate(user)

    except ValidationError as e:
        logger.error(f"Validation error in get_user_by_id for user_id {user_id}: {str(e)}")
        raise
    except UserNotFoundError as e:
        logger.error(f"Resource not found in get_user_by_id for user_id {user_id}: {str(e)}")
        raise
    except DatabaseError as e:
        logger.error(f"Database error in get_user_by_id for user_id {user_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_user_by_id for user_id {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error retrieving user"
        )

async def get_users(
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.VIEW_USER]))
) -> List[UserOut]:
    """
    Retrieve a list of active users with pagination. Requires VIEW_USER permission.
    """
    try:
        if skip < 0 or (limit is not None and limit <= 0):
            raise ValidationError(detail="Invalid pagination parameters")

        limit = limit or settings.DEFAULT_PAGE_SIZE
        query = select(Users).where(
            Users.is_active == True,
            Users.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        users = result.scalars().all()

        logger.info(f"Retrieved {len(users)} users")
        return [UserOut.model_validate(user) for user in users]

    except ValidationError as e:
        logger.error(f"Validation error in get_users: {str(e)}")
        raise
    except DatabaseError as e:
        logger.error(f"Database error in get_users: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error retrieving users"
        )

async def update_user(
    user_id: int,
    user_update: UserUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    log_service: SystemLogService = Depends(get_system_log_service),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.UPDATE_USER]))
) -> UserOut:
    """
    Update a user with validation and logging. Requires UPDATE_USER permission.
    """
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user ID")

        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        db_user = result.scalar_one_or_none()

        if not db_user:
            raise UserNotFoundError(user_id=user_id)

        update_data = user_update.model_dump(exclude_none=True)
        if "email" in update_data:
            query = select(Users).where(
                Users.email == update_data["email"],
                Users.user_id != user_id,
                Users.is_active == True,
                Users.deleted_at == None
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise ResourceConflictError(detail="Email already registered")

        if "manager_id" in update_data and update_data["manager_id"] is not None:
            await validate_user_exists(db, update_data["manager_id"])

        if "employee_type" in update_data and update_data["employee_type"] is not None:
            if update_data["employee_type"] not in [e.value for e in EmployeeType]:
                raise ValidationError(detail=f"Invalid employee_type. Must be one of: {[e.value for e in EmployeeType]}")

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

        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE,
            table_affected="users",
            record_id=user_id,
            old_values=old_values,
            new_values=db_user.__dict__,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent")
        )
        await log_service.create_system_log(log, current_user, request)

        logger.info(f"User updated, user_id: {user_id}")
        return UserOut.model_validate(db_user)

    except ValidationError as e:
        logger.error(f"Validation error in update_user for user_id {user_id}: {str(e)}")
        raise
    except UserNotFoundError as e:
        logger.error(f"Resource not found in update_user for user_id {user_id}: {str(e)}")
        raise
    except ResourceConflictError as e:
        logger.error(f"Conflict error in update_user for user_id {user_id}: {str(e)}")
        raise
    except DatabaseError as e:
        logger.error(f"Database error in update_user for user_id {user_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in update_user for user_id {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error updating user"
        )

async def delete_user(
    user_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    log_service: SystemLogService = Depends(get_system_log_service),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.DELETE_USER]))
) -> None:
    """
    Soft delete a user with validation and logging. Requires DELETE_USER permission.
    """
    try:
        if user_id <= 0:
            raise ValidationError(detail="Invalid user ID")

        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        db_user = result.scalar_one_or_none()

        if not db_user:
            raise UserNotFoundError(user_id=user_id)

        query = select(Users).where(
            Users.manager_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalars().all():
            raise BusinessLogicError(detail="Cannot delete user with active subordinates")

        db_user.is_active = False
        db_user.deleted_at = datetime.now(timezone.utc)
        db.add(db_user)
        await db.commit()

        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE,
            table_affected="users",
            record_id=user_id,
            old_values=db_user.__dict__,
            new_values=None,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent")
        )
        await log_service.create_system_log(log, current_user, request)

        logger.info(f"User soft deleted, user_id: {user_id}")

    except ValidationError as e:
        logger.error(f"Validation error in delete_user for user_id {user_id}: {str(e)}")
        raise
    except UserNotFoundError as e:
        logger.error(f"Resource not found in delete_user for user_id {user_id}: {str(e)}")
        raise
    except BusinessLogicError as e:
        logger.error(f"Business logic error in delete_user for user_id {user_id}: {str(e)}")
        raise
    except DatabaseError as e:
        logger.error(f"Database error in delete_user for user_id {user_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in delete_user for user_id {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error deleting user"
        )