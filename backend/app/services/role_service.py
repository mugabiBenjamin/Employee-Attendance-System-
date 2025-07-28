from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.roles import Roles
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.schemas.role import RoleCreate, RoleUpdate, RoleOut
from app.core.config import settings
from app.core.enums import SystemAction
import logging

logger = logging.getLogger(__name__)

async def create_role(db: AsyncSession, role: RoleCreate, current_user: Users) -> RoleOut:
    """
    Create a new role with validation and logging.
    """
    try:
        # Validate role_name
        if role.role_name not in ['Employee', 'Manager', 'HR', 'Admin', 'Super_Admin']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role name. Must be one of: Employee, Manager, HR, Admin, Super_Admin"
            )

        # Check for existing role
        query = select(Roles).where(
            Roles.role_name == role.role_name,
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role name already exists"
            )

        # Validate permissions
        invalid_permissions = [p for p in role.permissions.keys() if p not in settings.PERMISSION_KEYS]
        if invalid_permissions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid permissions: {', '.join(invalid_permissions)}"
            )

        # Create role
        db_role = Roles(
            role_name=role.role_name,
            description=role.description,
            permissions=role.permissions,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_role)
        await db.commit()
        await db.refresh(db_role)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.INSERT,
            table_affected="roles",
            record_id=db_role.role_id,
            old_values=None,
            new_values=db_role.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Role created, role_id: {db_role.role_id}, role_name: {db_role.role_name}")
        return RoleOut.model_validate(db_role)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating role: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating role"
        )

async def get_role_by_id(db: AsyncSession, role_id: int) -> Optional[RoleOut]:
    """
    Retrieve a role by ID.
    """
    try:
        query = select(Roles).where(
            Roles.role_id == role_id,
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        role = result.scalar_one_or_none()

        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found"
            )

        return RoleOut.model_validate(role)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving role"
        )

async def get_roles(db: AsyncSession, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[RoleOut]:
    """
    Retrieve a list of active roles with pagination.
    """
    try:
        query = select(Roles).where(
            Roles.is_active == True,
            Roles.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        roles = result.scalars().all()

        logger.info(f"Retrieved {len(roles)} roles")
        return [RoleOut.model_validate(role) for role in roles]

    except Exception as e:
        logger.error(f"Error retrieving roles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving roles"
        )

async def update_role(db: AsyncSession, role_id: int, role_update: RoleUpdate, current_user: Users) -> RoleOut:
    """
    Update a role with validation and logging.
    """
    try:
        # Retrieve role
        query = select(Roles).where(
            Roles.role_id == role_id,
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        db_role = result.scalar_one_or_none()

        if not db_role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found"
            )

        # Check for duplicate role name if updated
        update_data = role_update.model_dump(exclude_none=True)
        if "role_name" in update_data:
            if update_data["role_name"] not in ['Employee', 'Manager', 'HR', 'Admin', 'Super_Admin']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid role name. Must be one of: Employee, Manager, HR, Admin, Super_Admin"
                )
            query = select(Roles).where(
                Roles.role_name == update_data["role_name"],
                Roles.role_id != role_id,
                Roles.is_active == True,
                Roles.deleted_at == None
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Role name already exists"
                )

        # Validate permissions if updated
        if "permissions" in update_data:
            invalid_permissions = [p for p in update_data["permissions"].keys() if p not in settings.PERMISSION_KEYS]
            if invalid_permissions:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid permissions: {', '.join(invalid_permissions)}"
                )

        # Store old values for logging
        old_values = db_role.__dict__.copy()

        # Apply updates
        for key, value in update_data.items():
            setattr(db_role, key, value)

        db_role.updated_at = datetime.now(timezone.utc)
        db.add(db_role)
        await db.commit()
        await db.refresh(db_role)

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.UPDATE,
            table_affected="roles",
            record_id=role_id,
            old_values=old_values,
            new_values=db_role.__dict__,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Role updated, role_id: {role_id}")
        return RoleOut.model_validate(db_role)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating role"
        )

async def delete_role(db: AsyncSession, role_id: int, current_user: Users) -> None:
    """
    Soft delete a role with logging.
    """
    try:
        query = select(Roles).where(
            Roles.role_id == role_id,
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        db_role = result.scalar_one_or_none()

        if not db_role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found"
            )

        db_role.is_active = False
        db_role.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        # Log action
        system_log = SystemLogs(
            user_id=current_user.user_id,
            action=SystemAction.DELETE,
            table_affected="roles",
            record_id=role_id,
            old_values=db_role.__dict__,
            new_values=None,
            ip_address=None,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Role soft deleted, role_id: {role_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting role"
        )