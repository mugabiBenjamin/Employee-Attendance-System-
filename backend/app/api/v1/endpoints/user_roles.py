from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, AsyncGenerator
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone
from app.core.database import AsyncSessionLocal
from app.models.user_roles import UserRoles
from app.models.users import Users
from app.models.roles import Roles
from app.core.security import check_user_permission
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-roles", tags=["User Roles"])

class UserRoleCreate(BaseModel):
    """Schema for creating a new user role assignment."""
    user_id: int
    role_id: int

    model_config = ConfigDict(from_attributes=True)

class UserRoleUpdate(BaseModel):
    """Schema for updating an existing user role assignment."""
    user_id: Optional[int] = None
    role_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class UserRoleOut(BaseModel):
    """Schema for user role assignment output."""
    user_role_id: int
    user_id: int
    role_id: int
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

@router.post("/", response_model=UserRoleOut, status_code=status.HTTP_201_CREATED, summary="Create user role assignment", description="Create a new user role assignment. Requires manage_user_roles permission or Admin/Super_Admin access.")
async def create_user_role(
    user_role: UserRoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserRoleOut:
    """
    Create a new user role assignment in the system.

    Args:
        user_role: User role assignment creation data.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        UserRoleOut: Created user role assignment details.

    Raises:
        HTTPException: If user lacks permission, user/role not found, or assignment exists.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "manage_user_roles")
        if not has_permission and not await is_admin_or_super_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create user role assignments")

        # Verify user exists
        query = select(Users).where(
            Users.user_id == user_role.user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Verify role exists
        query = select(Roles).where(
            Roles.role_id == user_role.role_id,
            Roles.is_active == True,
            Roles.deleted_at == None
        )
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

        # Check for existing assignment
        query = select(UserRoles).where(
            UserRoles.user_id == user_role.user_id,
            UserRoles.role_id == user_role.role_id,
            UserRoles.is_active == True
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User role assignment already exists")

        db_user_role = UserRoles(
            **user_role.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_user_role)
        await db.commit()
        await db.refresh(db_user_role)

        logger.info(f"User role assignment created, user_role_id: {db_user_role.user_role_id}, user_id: {db_user_role.user_id}")
        return UserRoleOut.model_validate(db_user_role)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user role assignment: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating user role assignment")

@router.get("/{user_role_id}", response_model=UserRoleOut, summary="Get user role assignment by ID", description="Retrieve user role assignment details. Requires view_user_roles permission or Admin/Super_Admin access.")
async def read_user_role(
    user_role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserRoleOut:
    """
    Get a specific user role assignment by its ID.

    Args:
        user_role_id: ID of the user role assignment to retrieve.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        UserRoleOut: User role assignment details.

    Raises:
        HTTPException: If user lacks permission or assignment not found.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "view_user_roles")
        if not has_permission and not await is_admin_or_super_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view user role assignments")

        query = select(UserRoles).where(
            UserRoles.user_role_id == user_role_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        )
        result = await db.execute(query)
        user_role = result.scalar_one_or_none()

        if not user_role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User role assignment not found")

        logger.info(f"Retrieved user role assignment, user_role_id: {user_role_id}")
        return UserRoleOut.model_validate(user_role)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user role assignment {user_role_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving user role assignment")

@router.get("/", response_model=List[UserRoleOut], summary="List user role assignments", description="Retrieve all user role assignments with pagination. Requires view_user_roles permission or Admin/Super_Admin access.")
async def read_user_roles(
    user_id: Optional[int] = None,
    role_id: Optional[int] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[UserRoleOut]:
    """
    Get a paginated list of user role assignments, optionally filtered by user or role.

    Args:
        user_id: Optional user ID to filter assignments.
        role_id: Optional role ID to filter assignments.
        skip: Number of records to skip (for pagination).
        limit: Maximum number of records to return.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        List[UserRoleOut]: List of user role assignment details.

    Raises:
        HTTPException: If user lacks permission or an error occurs.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "view_user_roles")
        if not has_permission and not await is_admin_or_super_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view user role assignments")

        query = select(UserRoles).where(
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        )
        if user_id:
            query = query.where(UserRoles.user_id == user_id)
        if role_id:
            query = query.where(UserRoles.role_id == role_id)
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        user_roles = result.scalars().all()

        logger.info(f"Retrieved {len(user_roles)} user role assignments")
        return [UserRoleOut.model_validate(user_role) for user_role in user_roles]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user role assignments: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving user role assignments")

@router.put("/{user_role_id}", response_model=UserRoleOut, summary="Update user role assignment", description="Update user role assignment information. Requires manage_user_roles permission or Admin/Super_Admin access.")
async def update_user_role(
    user_role_id: int,
    user_role_update: UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserRoleOut:
    """
    Update an existing user role assignment's information.

    Args:
        user_role_id: ID of the user role assignment to update.
        user_role_update: Updated user role assignment data.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        UserRoleOut: Updated user role assignment details.

    Raises:
        HTTPException: If user lacks permission, assignment not found, or conflicts exist.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "manage_user_roles")
        if not has_permission and not await is_admin_or_super_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update user role assignments")

        query = select(UserRoles).where(
            UserRoles.user_role_id == user_role_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        )
        result = await db.execute(query)
        user_role = result.scalar_one_or_none()

        if not user_role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User role assignment not found")

        update_data = user_role_update.model_dump(exclude_none=True)
        if "user_id" in update_data:
            query = select(Users).where(
                Users.user_id == update_data["user_id"],
                Users.is_active == True,
                Users.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if "role_id" in update_data:
            query = select(Roles).where(
                Roles.role_id == update_data["role_id"],
                Roles.is_active == True,
                Roles.deleted_at == None
            )
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

        if update_data.get("user_id") or update_data.get("role_id"):
            query = select(UserRoles).where(
                UserRoles.user_id == update_data.get("user_id", user_role.user_id),
                UserRoles.role_id == update_data.get("role_id", user_role.role_id),
                UserRoles.is_active == True,
                UserRoles.user_role_id != user_role_id
            )
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User role assignment already exists")

        for key, value in update_data.items():
            setattr(user_role, key, value)

        user_role.updated_at = datetime.now(timezone.utc)
        db.add(user_role)
        await db.commit()
        await db.refresh(user_role)

        logger.info(f"User role assignment updated, user_role_id: {user_role_id}")
        return UserRoleOut.model_validate(user_role)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user role assignment {user_role_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating user role assignment")

@router.delete("/{user_role_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete user role assignment", description="Soft delete a user role assignment. Requires manage_user_roles permission or Admin/Super_Admin access.")
async def delete_user_role(
    user_role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    """
    Soft delete a user role assignment from the system.

    Args:
        user_role_id: ID of the user role assignment to delete.
        db: Async database session.
        current_user: Current authenticated user.

    Raises:
        HTTPException: If user lacks permission or assignment not found.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "manage_user_roles")
        if not has_permission and not await is_admin_or_super_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete user role assignments")

        query = select(UserRoles).where(
            UserRoles.user_role_id == user_role_id,
            UserRoles.is_active == True,
            UserRoles.deleted_at == None
        )
        result = await db.execute(query)
        user_role = result.scalar_one_or_none()

        if not user_role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User role assignment not found")

        user_role.is_active = False
        user_role.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"User role assignment soft deleted, user_role_id: {user_role_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user role assignment {user_role_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting user role assignment")