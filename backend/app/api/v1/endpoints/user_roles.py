from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime, timezone
from app.core.database import get_db
from app.models.user_roles import UserRoles
from app.models.users import Users
from app.models.roles import Roles
from app.core.permissions import check_permissions
from app.core.security import get_current_active_user
from app.core.config import settings
from app.core.enums import Permission
from app.schemas.user_role import UserRoleCreate, UserRoleUpdate, UserRoleOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-roles", tags=["User Roles"])

async def is_admin_or_super_admin(db: AsyncSession, user: Users) -> bool:
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

@router.post("/", response_model=UserRoleOut, status_code=status.HTTP_201_CREATED, summary="Create user role assignment")
async def create_user_role(
    user_role: UserRoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserRoleOut:
    try:
        has_permission = await check_permissions([Permission.MANAGE_USER_ROLES.value], current_user, db)
        if not has_permission and not await is_admin_or_super_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create user role assignments")

        query = select(Users).where(Users.user_id == user_role.user_id, Users.is_active == True, Users.deleted_at == None)
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        query = select(Roles).where(Roles.role_id == user_role.role_id, Roles.is_active == True, Roles.deleted_at == None)
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

        query = select(UserRoles).where(
            UserRoles.user_id == user_role.user_id,
            UserRoles.role_id == user_role.role_id,
            UserRoles.is_active == True
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User role assignment already exists")

        db_user_role = UserRoles(
            user_id=user_role.user_id,
            role_id=user_role.role_id,
            assigned_by=user_role.assigned_by,
            assigned_at=datetime.now(timezone.utc),
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

@router.get("/{user_role_id}", response_model=UserRoleOut, summary="Get user role assignment by ID")
async def read_user_role(
    user_role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserRoleOut:
    try:
        has_permission = await check_permissions([Permission.VIEW_USER_ROLES.value], current_user, db)
        if not has_permission and not await is_admin_or_super_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view user role assignments")

        query = select(UserRoles).where(UserRoles.user_role_id == user_role_id, UserRoles.is_active == True, UserRoles.deleted_at == None)
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

@router.get("/", response_model=List[UserRoleOut], summary="List user role assignments")
async def read_user_roles(
    user_id: Optional[int] = None,
    role_id: Optional[int] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[UserRoleOut]:
    try:
        has_permission = await check_permissions([Permission.VIEW_USER_ROLES.value], current_user, db)
        if not has_permission and not await is_admin_or_super_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view user role assignments")

        query = select(UserRoles).where(UserRoles.is_active == True, UserRoles.deleted_at == None)
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

@router.put("/{user_role_id}", response_model=UserRoleOut, summary="Update user role assignment")
async def update_user_role(
    user_role_id: int,
    user_role_update: UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserRoleOut:
    try:
        has_permission = await check_permissions([Permission.MANAGE_USER_ROLES.value], current_user, db)
        if not has_permission and not await is_admin_or_super_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update user role assignments")

        query = select(UserRoles).where(UserRoles.user_role_id == user_role_id, UserRoles.is_active == True, UserRoles.deleted_at == None)
        result = await db.execute(query)
        user_role = result.scalar_one_or_none()

        if not user_role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User role assignment not found")

        update_data = user_role_update.model_dump(exclude_none=True)
        if "user_id" in update_data:
            query = select(Users).where(Users.user_id == update_data["user_id"], Users.is_active == True, Users.deleted_at == None)
            result = await db.execute(query)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if "role_id" in update_data:
            query = select(Roles).where(Roles.role_id == update_data["role_id"], Roles.is_active == True, Roles.deleted_at == None)
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

@router.delete("/{user_role_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete user role assignment")
async def delete_user_role(
    user_role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    try:
        has_permission = await check_permissions([Permission.MANAGE_USER_ROLES.value], current_user, db)
        if not has_permission and not await is_admin_or_super_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete user role assignments")

        query = select(UserRoles).where(UserRoles.user_role_id == user_role_id, UserRoles.is_active == True, UserRoles.deleted_at == None)
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