from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, AsyncGenerator
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, timezone
from app.core.database import AsyncSessionLocal
from app.models.roles import Roles
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.core.security import check_user_permission
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/roles", tags=["Roles"])

class RoleCreate(BaseModel):
    """Schema for creating a new role."""
    role_name: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=500)

    model_config = ConfigDict(from_attributes=True)

class RoleUpdate(BaseModel):
    """Schema for updating an existing role."""
    role_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)

    model_config = ConfigDict(from_attributes=True)

class RoleOut(BaseModel):
    """Schema for role output."""
    role_id: int
    role_name: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    created_at: datetime
    updated_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to provide an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {str(e)}")
            await session.rollback()
            raise
        finally:
            await session.close()

async def get_current_active_user(db: AsyncSession = Depends(get_db)) -> Users:
    """Dependency to get the current active user."""
    query = select(Users).where(Users.is_active == True, Users.deleted_at == None)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")
    return user

async def is_admin_or_super_admin(db: AsyncSession, user: Users) -> bool:
    """
    Check if the user has Admin or Super_Admin role.

    Args:
        db: Async database session.
        user: Current user object.

    Returns:
        bool: True if user has Admin or Super_Admin role, False otherwise.
    """
    try:
        query = select(UserRoles).join(Roles).where(
            UserRoles.user_id == user.user_id,
            UserRoles.is_active == True,
            Roles.role_name.in_(["Admin", "Super_Admin"]),
            Roles.is_active == True
        )
        result = await db.execute(query)
        return result.scalar_one_or_none() is not None
    except Exception as e:
        logger.error(f"Error checking admin role for user_id {user.user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error checking user role")

@router.post("/", response_model=RoleOut, status_code=status.HTTP_201_CREATED, summary="Create new role", description="Create a new role. Requires manage_roles permission or Admin/Super_Admin access.")
async def create_role(
    role: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> RoleOut:
    """
    Create a new role in the system.

    Args:
        role: Role creation data.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        RoleOut: Created role details.

    Raises:
        HTTPException: If user lacks permission or role name already exists.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "manage_roles")
        if not has_permission and not await is_admin_or_super_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create roles")

        query = select(Roles).where(
            Roles.role_name == role.role_name,
            Roles.is_active == True
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role name already exists")

        db_role = Roles(
            **role.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_role)
        await db.commit()
        await db.refresh(db_role)

        logger.info(f"Role created, role_id: {db_role.role_id}, role_name: {db_role.role_name}")
        return RoleOut.model_validate(db_role)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating role: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating role")

@router.get("/{role_id}", response_model=RoleOut, summary="Get role by ID", description="Retrieve role details. Requires view_roles permission or Admin/Super_Admin access.")
async def read_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> RoleOut:
    """
    Get a specific role by its ID.

    Args:
        role_id: ID of the role to retrieve.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        RoleOut: Role details.

    Raises:
        HTTPException: If user lacks permission or role not found.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "view_roles")
        if not has_permission and not await is_admin_or_super_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view roles")

        query = select(Roles).where(
            Roles.role_id == role_id,
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        role = result.scalar_one_or_none()

        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

        logger.info(f"Retrieved role, role_id: {role_id}")
        return RoleOut.model_validate(role)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving role {role_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving role")

@router.get("/", response_model=List[RoleOut], summary="List all roles", description="Retrieve all roles with pagination. Requires view_roles permission or Admin/Super_Admin access.")
async def read_roles(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[RoleOut]:
    """
    Get a paginated list of all roles.

    Args:
        skip: Number of records to skip (for pagination).
        limit: Maximum number of records to return.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        List[RoleOut]: List of role details.

    Raises:
        HTTPException: If user lacks permission or an error occurs.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "view_roles")
        if not has_permission and not await is_admin_or_super_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view roles")

        query = select(Roles).where(
            Roles.is_active == True,
            Roles.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        roles = result.scalars().all()

        logger.info(f"Retrieved {len(roles)} roles")
        return [RoleOut.model_validate(role) for role in roles]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving roles: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving roles")

@router.put("/{role_id}", response_model=RoleOut, summary="Update role", description="Update role information. Requires manage_roles permission or Admin/Super_Admin access.")
async def update_role(
    role_id: int,
    role_update: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> RoleOut:
    """
    Update an existing role's information.

    Args:
        role_id: ID of the role to update.
        role_update: Updated role data.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        RoleOut: Updated role details.

    Raises:
        HTTPException: If user lacks permission, role not found, or role name exists.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "manage_roles")
        if not has_permission and not await is_admin_or_super_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update roles")

        query = select(Roles).where(
            Roles.role_id == role_id,
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        role = result.scalar_one_or_none()

        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

        update_data = role_update.model_dump(exclude_none=True)
        if "role_name" in update_data and update_data["role_name"] != role.role_name:
            query = select(Roles).where(
                Roles.role_name == update_data["role_name"],
                Roles.is_active == True
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role name already exists")

        for key, value in update_data.items():
            setattr(role, key, value)

        role.updated_at = datetime.now(timezone.utc)
        db.add(role)
        await db.commit()
        await db.refresh(role)

        logger.info(f"Role updated, role_id: {role_id}")
        return RoleOut.model_validate(role)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating role {role_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating role")

@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete role", description="Soft delete a role. Requires manage_roles permission or Admin/Super_Admin access.")
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    """
    Soft delete a role from the system.

    Args:
        role_id: ID of the role to delete.
        db: Async database session.
        current_user: Current authenticated user.

    Raises:
        HTTPException: If user lacks permission, role not found, or role is in use.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "manage_roles")
        if not has_permission and not await is_admin_or_super_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete roles")

        query = select(Roles).where(
            Roles.role_id == role_id,
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        role = result.scalar_one_or_none()

        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

        # Check if role is assigned to any users
        query = select(UserRoles).where(
            UserRoles.role_id == role_id,
            UserRoles.is_active == True
        )
        result = await db.execute(query)
        if result.scalars().first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete role; it is assigned to users")

        role.is_active = False
        role.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Role soft deleted, role_id: {role_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting role {role_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting role")
