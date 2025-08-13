from typing import List, Optional
from fastapi import HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.users import Users
from app.schemas.user import UserCreate, UserUpdate, UserOut
from app.core.security import get_password_hash
from app.core.enums import SystemAction, Permission
from app.core.security import get_current_user
from app.core.permissions import require_permissions
from app.services.system_log_service import SystemLogService, get_system_log_service
from app.schemas.system_log import SystemLogCreate
from app.core.validators import validate_user_exists
from app.core.config import Settings, get_settings
import logging

logger = logging.getLogger(__name__)

async def create_user(
    db: AsyncSession,
    user: UserCreate,
    current_user: Users = Depends(get_current_user),
    _: str = Depends(require_permissions([Permission.CREATE_USER])),
    log_service: SystemLogService = Depends(get_system_log_service),
    settings: Settings = Depends(get_settings)
) -> UserOut:
    """
    Create a new user with validation and logging. Requires CREATE_USER permission.
    """
    try:
        # Check for existing email
        query = select(Users).where(
            Users.email == user.email,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Validate manager_id if provided
        if user.manager_id:
            await validate_user_exists(db, user.manager_id)

        # Create user with hashed password
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
            ip_address=None
        )
        await log_service.create_system_log(log, current_user)

        logger.info(f"User created, user_id: {db_user.user_id}, email: {db_user.email}")
        return UserOut.model_validate(db_user)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating user"
        )

async def get_user_by_id(
    db: AsyncSession,
    user_id: int,
    _: str = Depends(require_permissions([Permission.VIEW_USER])),
    settings: Settings = Depends(get_settings)
) -> Optional[UserOut]:
    """
    Retrieve a user by ID. Requires VIEW_USER permission.
    """
    try:
        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        return UserOut.model_validate(user)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving user"
        )

async def get_users(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    _: str = Depends(require_permissions([Permission.VIEW_USER])),
    settings: Settings = Depends(get_settings)
) -> List[UserOut]:
    """
    Retrieve a list of active users with pagination. Requires VIEW_USER permission.
    """
    try:
        query = select(Users).where(
            Users.is_active == True,
            Users.deleted_at == None
        ).offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        result = await db.execute(query)
        users = result.scalars().all()

        logger.info(f"Retrieved {len(users)} users")
        return [UserOut.model_validate(user) for user in users]

    except Exception as e:
        logger.error(f"Error retrieving users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving users"
        )

async def update_user(
    db: AsyncSession,
    user_id: int,
    user_update: UserUpdate,
    current_user: Users = Depends(get_current_user),
    _: str = Depends(require_permissions([Permission.UPDATE_USER])),
    log_service: SystemLogService = Depends(get_system_log_service),
    settings: Settings = Depends(get_settings)
) -> UserOut:
    """
    Update a user with validation and logging. Requires UPDATE_USER permission.
    """
    try:
        # Retrieve user
        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        db_user = result.scalar_one_or_none()

        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Check for duplicate email if updated
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
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )

        # Validate manager_id if updated
        if "manager_id" in update_data and update_data["manager_id"] is not None:
            await validate_user_exists(db, update_data["manager_id"])

        # Store old values for logging
        old_values = db_user.__dict__.copy()

        # Apply updates
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

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE,
            table_affected="users",
            record_id=user_id,
            old_values=old_values,
            new_values=db_user.__dict__,
            ip_address=None
        )
        await log_service.create_system_log(log, current_user)

        logger.info(f"User updated, user_id: {user_id}")
        return UserOut.model_validate(db_user)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating user"
        )

async def delete_user(
    db: AsyncSession,
    user_id: int,
    current_user: Users = Depends(get_current_user),
    _: str = Depends(require_permissions([Permission.DELETE_USER])),
    log_service: SystemLogService = Depends(get_system_log_service),
    settings: Settings = Depends(get_settings)
) -> None:
    """
    Soft delete a user with validation and logging. Requires DELETE_USER permission.
    """
    try:
        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        db_user = result.scalar_one_or_none()

        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Prevent deletion if user has active subordinates
        query = select(Users).where(
            Users.manager_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalars().all():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete user with active subordinates"
            )

        db_user.is_active = False
        db_user.deleted_at = datetime.now(timezone.utc)
        db.add(db_user)
        await db.commit()

        # Log action
        log = SystemLogCreate(
            user_id=current_user.user_id,
            action=SystemAction.DELETE,
            table_affected="users",
            record_id=user_id,
            old_values=db_user.__dict__,
            new_values=None,
            ip_address=None
        )
        await log_service.create_system_log(log, current_user)

        logger.info(f"User soft deleted, user_id: {user_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting user"
        )