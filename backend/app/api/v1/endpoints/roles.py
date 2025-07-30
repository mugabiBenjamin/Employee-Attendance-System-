from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timezone
from app.core.database import get_db
from app.models.roles import Roles
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.config import settings
from app.core.enums import Permission
from app.schemas.role import RoleCreate, RoleUpdate, RoleOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/roles", tags=["Roles"])

@router.post("/", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
@require_permissions([Permission.MANAGE_ROLES])
async def create_role(
    role: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
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
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role name already exists"
            )

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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating role: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating role"
        )

@router.get("/{role_id}", response_model=RoleOut)
@require_permissions([Permission.MANAGE_ROLES])
async def get_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> RoleOut:
    """Get role by ID."""
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

@router.get("/", response_model=List[RoleOut])
@require_permissions([Permission.MANAGE_ROLES])
async def list_roles(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[RoleOut]:
    """List all active roles."""
    try:
        query = select(Roles).where(
            Roles.is_active == True,
            Roles.deleted_at == None
        ).offset(skip).limit(limit)
        
        result = await db.execute(query)
        roles = result.scalars().all()

        return [RoleOut.model_validate(role) for role in roles]

    except Exception as e:
        logger.error(f"Error retrieving roles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving roles"
        )

@router.put("/{role_id}", response_model=RoleOut)
@require_permissions([Permission.MANAGE_ROLES])
async def update_role(
    role_id: int,
    role_update: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> RoleOut:
    """Update an existing role."""
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

        update_data = role_update.model_dump(exclude_none=True)
        
        # Check for name conflicts if updating role_name
        if "role_name" in update_data and update_data["role_name"] != role.role_name:
            query = select(Roles).where(
                Roles.role_name == update_data["role_name"],
                Roles.is_active == True
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Role name already exists"
                )

        # Update fields
        for key, value in update_data.items():
            setattr(role, key, value)

        role.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(role)

        logger.info(f"Updated role: {role_id}")
        return RoleOut.model_validate(role)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating role"
        )

@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions([Permission.MANAGE_ROLES])
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    """Soft delete a role."""
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

        # Check if role is assigned to users
        query = select(UserRoles).where(
            UserRoles.role_id == role_id,
            UserRoles.is_active == True
        )
        result = await db.execute(query)
        if result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete role; it is assigned to users"
            )

        role.is_active = False
        role.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Deleted role: {role_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting role"
        )