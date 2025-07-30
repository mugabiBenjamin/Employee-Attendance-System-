from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.user_roles import UserRoles
from app.models.users import Users
from app.models.roles import Roles
from app.models.system_logs import SystemLogs
from app.schemas.user_role import UserRoleCreate, UserRoleUpdate, UserRoleOut
from app.core.config import settings
from app.core.enums import SystemAction
from app.core.exceptions import UserNotFoundError, RoleNotFoundError
import logging

logger = logging.getLogger(__name__)

async def create_user_role(db: AsyncSession, user_role: UserRoleCreate, current_user: Users) -> UserRoleOut:
    """
    Assign a role to a user with validation and logging.
    """
    try:
        # Validate user
        query = select(Users).where(
            Users.user_id == user_role.user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise UserNotFoundError(detail="User not found")

        # Validate role
        query = select(Roles).where(
            Roles.role_id == user_role.role_id,
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise RoleNotFoundError(detail="Role not found")

        # Check for existing assignment
        query = select(UserRoles).where(
            UserRoles.user_id == user_role.user_id,
            UserRoles.role_id == user_role.role_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already assigned to this role"
            )

        # Create user-role assignment
        db_user_role = UserRoles(
            user_id=user_role.user_id,
            role_id=user_role.role_id,
            assigned_by=current_user.user_id,
            is_active=user_role.is_active,
            assigned_at=datetime.now(timezone.utc),
            deleted_at=None
        )
        db.add(db_user_role)
        await db.commit()
        await db.refresh(db_user_role)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="user_roles",
            record_id=db_user_role.user_role_id,
            old_values=None,
            new_values=db_user_role.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"User role assignment created, user_role_id: {db_user_role.user_role_id}, user_id: {user_role.user_id}")
        return UserRoleOut.model_validate(db_user_role)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user role assignment for user_id {user_role.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating user role assignment"
        )

async def get_user_role_by_id(db: AsyncSession, user_role_id: int) -> Optional[UserRoleOut]:
    """
    Retrieve a user-role assignment by ID.
    """
    try:
        query = select(UserRoles).where(
            UserRoles.user_role_id == user_role_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        )
        result = await db.execute(query)
        user_role = result.scalar_one_or_none()

        if not user_role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User role assignment not found"
            )

        return UserRoleOut.model_validate(user_role)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user role assignment {user_role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving user role assignment"
        )

async def get_user_roles(db: AsyncSession, user_id: int, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[UserRoleOut]:
    """
    Retrieve a list of role assignments for a user with pagination.
    """
    try:
        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise UserNotFoundError(detail="User not found")

        query = select(UserRoles).where(
            UserRoles.user_id == user_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        user_roles = result.scalars().all()

        logger.info(f"Retrieved {len(user_roles)} role assignments for user_id: {user_id}")
        return [UserRoleOut.model_validate(ur) for ur in user_roles]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving role assignments for user_id {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving role assignments"
        )

async def update_user_role(db: AsyncSession, user_role_id: int, user_role_update: UserRoleUpdate, current_user: Users) -> UserRoleOut:
    """
    Update a user-role assignment with validation and logging.
    """
    try:
        # Retrieve user-role assignment
        query = select(UserRoles).where(
            UserRoles.user_role_id == user_role_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        )
        result = await db.execute(query)
        db_user_role = result.scalar_one_or_none()

        if not db_user_role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User role assignment not found"
            )

        # Validate user if updated
        update_data = user_role_update.model_dump(exclude_none=True)
        if "user_id" in update_data:
            query = select(Users).where(
                Users.user_id == update_data["user_id"],
                Users.is_active == True,
                Users.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise UserNotFoundError(detail="User not found")

        # Validate role if updated
        if "role_id" in update_data:
            query = select(Roles).where(
                Roles.role_id == update_data["role_id"],
                Roles.is_active == True,
                Roles.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise RoleNotFoundError(detail="Role not found")

            # Check for existing assignment
            query = select(UserRoles).where(
                UserRoles.user_id == (update_data.get("user_id", db_user_role.user_id)),
                UserRoles.role_id == update_data["role_id"],
                UserRoles.user_role_id != user_role_id,
                UserRoles.is_active == True,
                UserRoles.deleted_at == None
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User is already assigned to this role"
                )

        # Store old values for logging
        old_values = db_user_role.__dict__.copy()

        # Apply updates
        for key, value in update_data.items():
            setattr(db_user_role, key, value)

        db_user_role.updated_at = datetime.now(timezone.utc)
        db.add(db_user_role)
        await db.commit()
        await db.refresh(db_user_role)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE,
            table_affected="user_roles",
            record_id=user_role_id,
            old_values=old_values,
            new_values=db_user_role.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"User role assignment updated, user_role_id: {user_role_id}")
        return UserRoleOut.model_validate(db_user_role)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user role assignment {user_role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating user role assignment"
        )

async def delete_user_role(db: AsyncSession, user_role_id: int, current_user: Users) -> None:
    """
    Soft delete a user-role assignment with logging.
    """
    try:
        query = select(UserRoles).where(
            UserRoles.user_role_id == user_role_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        )
        result = await db.execute(query)
        db_user_role = result.scalar_one_or_none()

        if not db_user_role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User role assignment not found"
            )

        # Prevent deletion of user's last role assignment
        query = select(UserRoles).where(
            UserRoles.user_id == db_user_role.user_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        )
        result = await db.execute(query)
        user_roles = result.scalars().all()
        
        if len(user_roles) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete user's last role assignment"
            )

        db_user_role.is_active = False
        db_user_role.deleted_at = datetime.now(timezone.utc)
        db.add(db_user_role)
        await db.commit()

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.DELETE,
            table_affected="user_roles",
            record_id=user_role_id,
            old_values=db_user_role.__dict__,
            new_values=None,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"User role assignment soft deleted, user_role_id: {user_role_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user role assignment {user_role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting user role assignment"
        )