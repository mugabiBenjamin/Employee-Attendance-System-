from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from typing import List
from datetime import datetime, timezone
from app.core.database import get_db
from app.models.roles import Roles
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.schemas.role import RoleCreate, RoleUpdate, RoleOut
from app.core.exceptions import ValidationError, DatabaseError, ResourceNotFoundError, ResourceConflictError, BusinessLogicError
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/roles", tags=["Roles"])

@router.post("/", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
@require_permissions([Permission.MANAGE_ROLES])
async def create_role(
    role: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> RoleOut:
    """Create a new role."""
    try:
        # Check if role name already exists
        query = select(Roles).where(
            Roles.role_name == role.role_name,
            Roles.is_active == True
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ResourceConflictError(detail="Role name already exists")

        db_role = Roles(
            role_name=role.role_name,
            description=role.description,
            permissions=role.permissions,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        
        db.add(db_role)
        await db.commit()
        await db.refresh(db_role)

        logger.info(f"Created role: {db_role.role_id}")
        return RoleOut.model_validate(db_role)

    except ResourceConflictError as e:
        logger.error(f"Conflict error in create_role: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in create_role: {str(e)}")
        raise DatabaseError(message="Database error creating role", original_error=e)
    except Exception as e:
        logger.error(f"Unexpected error in create_role: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error creating role"
        )

@router.get("/{role_id}", response_model=RoleOut)
@require_permissions([Permission.MANAGE_ROLES])
async def get_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> RoleOut:
    """Get role by ID."""
    try:
        if role_id <= 0:
            raise ValidationError(detail="Invalid role ID")

        query = select(Roles).where(
            Roles.role_id == role_id,
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        role = result.scalar_one_or_none()

        if not role:
            raise ResourceNotFoundError(resource="Role", identifier=str(role_id))

        return RoleOut.model_validate(role)

    except ValidationError as e:
        logger.error(f"Validation error in get_role for role_id {role_id}: {str(e)}")
        raise
    except ResourceNotFoundError as e:
        logger.error(f"Resource not found in get_role for role_id {role_id}: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_role for role_id {role_id}: {str(e)}")
        raise DatabaseError(message="Database error retrieving role", original_error=e)
    except Exception as e:
        logger.error(f"Unexpected error in get_role for role_id {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error retrieving role"
        )

@router.get("/", response_model=List[RoleOut])
@require_permissions([Permission.MANAGE_ROLES])
async def list_roles(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[RoleOut]:
    """List all active roles with pagination."""
    try:
        if skip < 0 or limit <= 0:
            raise ValidationError(detail="Invalid pagination parameters")

        query = select(Roles).where(
            Roles.is_active == True,
            Roles.deleted_at == None
        ).offset(skip).limit(limit or settings.DEFAULT_PAGE_SIZE)
        
        result = await db.execute(query)
        roles = result.scalars().all()

        logger.info(f"Retrieved {len(roles)} roles")
        return [RoleOut.model_validate(role) for role in roles]

    except ValidationError as e:
        logger.error(f"Validation error in list_roles: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in list_roles: {str(e)}")
        raise DatabaseError(message="Database error retrieving roles", original_error=e)
    except Exception as e:
        logger.error(f"Unexpected error in list_roles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error retrieving roles"
        )

@router.put("/{role_id}", response_model=RoleOut)
@require_permissions([Permission.MANAGE_ROLES])
async def update_role(
    role_id: int,
    role_update: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> RoleOut:
    """Update an existing role."""
    try:
        if role_id <= 0:
            raise ValidationError(detail="Invalid role ID")

        query = select(Roles).where(
            Roles.role_id == role_id,
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        role = result.scalar_one_or_none()

        if not role:
            raise ResourceNotFoundError(resource="Role", identifier=str(role_id))

        update_data = role_update.model_dump(exclude_none=True)
        
        # Check for name conflicts if updating role_name
        if "role_name" in update_data and update_data["role_name"] != role.role_name:
            query = select(Roles).where(
                Roles.role_name == update_data["role_name"],
                Roles.is_active == True
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise ResourceConflictError(detail="Role name already exists")

        # Update fields
        for key, value in update_data.items():
            setattr(role, key, value)

        role.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(role)

        logger.info(f"Updated role: {role_id}")
        return RoleOut.model_validate(role)

    except ValidationError as e:
        logger.error(f"Validation error in update_role for role_id {role_id}: {str(e)}")
        raise
    except ResourceNotFoundError as e:
        logger.error(f"Resource not found in update_role for role_id {role_id}: {str(e)}")
        raise
    except ResourceConflictError as e:
        logger.error(f"Conflict error in update_role for role_id {role_id}: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in update_role for role_id {role_id}: {str(e)}")
        raise DatabaseError(message="Database error updating role", original_error=e)
    except Exception as e:
        logger.error(f"Unexpected error in update_role for role_id {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error updating role"
        )

@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions([Permission.MANAGE_ROLES])
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> None:
    """Soft delete a role."""
    try:
        if role_id <= 0:
            raise ValidationError(detail="Invalid role ID")

        query = select(Roles).where(
            Roles.role_id == role_id,
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        role = result.scalar_one_or_none()

        if not role:
            raise ResourceNotFoundError(resource="Role", identifier=str(role_id))

        # Check if role is assigned to users
        query = select(UserRoles).where(
            UserRoles.role_id == role_id,
            UserRoles.is_active == True
        )
        result = await db.execute(query)
        if result.scalars().first():
            raise BusinessLogicError(detail="Cannot delete role; it is assigned to users")

        role.is_active = False
        role.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Deleted role: {role_id}")

    except ValidationError as e:
        logger.error(f"Validation error in delete_role for role_id {role_id}: {str(e)}")
        raise
    except ResourceNotFoundError as e:
        logger.error(f"Resource not found in delete_role for role_id {role_id}: {str(e)}")
        raise
    except BusinessLogicError as e:
        logger.error(f"Business logic error in delete_role for role_id {role_id}: {str(e)}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in delete_role for role_id {role_id}: {str(e)}")
        raise DatabaseError(message="Database error deleting role", original_error=e)
    except Exception as e:
        logger.error(f"Unexpected error in delete_role for role_id {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error deleting role"
        )