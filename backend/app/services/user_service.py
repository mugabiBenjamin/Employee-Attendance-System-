from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.schemas.user import UserCreate, UserUpdate, UserOut
from app.core.config import settings
from app.core.security import get_password_hash
from app.core.enums import SystemAction
import logging

logger = logging.getLogger(__name__)

class UserCreateInternal(BaseModel):
    email: str
    password_hash: str
    first_name: str
    last_name: str
    phone_number: Optional[str] = None
    job_title: Optional[str] = None
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)

async def create_user(db: AsyncSession, user: UserCreate, current_user: Users) -> UserOut:
    """
    Create a new user with validation and logging.
    """
    try:
        # Check for existing email
        query = select(Users).where(Users.email == user.email)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Create user with hashed password
        hashed_password = get_password_hash(user.password)
        db_user = Users(
            **UserCreateInternal(
                **user.model_dump(exclude={"password"}),
                password_hash=hashed_password
            ).model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.USER_CREATED,
            table_affected="users",
            record_id=db_user.user_id,
            old_values=None,
            new_values=db_user.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

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

async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[UserOut]:
    """
    Retrieve a user by ID.
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
            return None

        return UserOut.model_validate(user)

    except Exception as e:
        logger.error(f"Error retrieving user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving user"
        )

async def get_users(db: AsyncSession, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[UserOut]:
    """
    Retrieve a list of active users with pagination.
    """
    try:
        query = select(Users).where(
            Users.is_active == True,
            Users.deleted_at == None
        ).offset(skip).limit(limit)
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

async def update_user(db: AsyncSession, user_id: int, user_update: UserUpdate, current_user: Users) -> UserOut:
    """
    Update a user with validation and logging.
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
                Users.user_id != user_id
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )

        # Handle password update if provided
        if "password" in update_data:
            update_data["password_hash"] = get_password_hash(update_data.pop("password"))

        # Store old values for logging
        old_values = db_user.__dict__.copy()

        # Apply updates
        for key, value in update_data.items():
            setattr(db_user, key, value)

        db_user.updated_at = datetime.now(timezone.utc)
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.USER_UPDATED,
            table_affected="users",
            record_id=user_id,
            old_values=old_values,
            new_values=db_user.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

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

async def delete_user(db: AsyncSession, user_id: int, current_user: Users) -> None:
    """
    Soft delete a user with logging.
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

        db_user.is_active = False
        db_user.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.USER_DELETED,
            table_affected="users",
            record_id=user_id,
            old_values=db_user.__dict__,
            new_values=None,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"User soft deleted, user_id: {user_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting user"
        )