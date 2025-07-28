from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timezone
from app.core.database import get_db
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.core.security import get_password_hash, get_current_active_user
from app.core.permissions import check_permissions
from app.core.config import settings
from app.core.enums import Permission
from app.schemas.user import UserCreate, UserUpdate, UserOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])

async def is_admin_or_hr(db: AsyncSession, user: Users) -> bool:
    try:
        query = select(UserRoles).join(Roles).where(
            UserRoles.user_id == user.user_id,
            UserRoles.is_active == True,
            Roles.role_name.in_(["HR", "Admin", "Super_Admin"]),
            Roles.is_active == True
        )
        result = await db.execute(query)
        return result.scalar_one_or_none() is not None
    except Exception as e:
        logger.error(f"Error checking admin/hr role for user_id {user.user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error checking user role")

@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="Create new user")
async def create_new_user(
    user: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserOut:
    try:
        has_permission = await check_permissions([Permission.MANAGE_USERS.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create users")

        query = select(Users).where(Users.email == user.email, Users.is_active == True)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

        db_user = Users(
            email=user.email,
            password_hash=get_password_hash(user.password_hash),
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

        logger.info(f"User created, user_id: {db_user.user_id}, email: {db_user.email}")
        return UserOut.model_validate(db_user)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating user")

@router.get("/{user_id}", response_model=UserOut, summary="Get user by ID")
async def read_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserOut:
    try:
        has_permission = await check_permissions([Permission.VIEW_USERS.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view users")

        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        logger.info(f"Retrieved user, user_id: {user_id}")
        return UserOut.model_validate(user)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user {user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving user")

@router.get("/", response_model=List[UserOut], summary="List all users")
async def read_users(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[UserOut]:
    try:
        has_permission = await check_permissions([Permission.VIEW_USERS.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view users")

        query = select(Users).where(
            Users.is_active == True,
            Users.deleted_at == None
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        users = result.scalars().all()

        logger.info(f"Retrieved {len(users)} users")
        return [UserOut.model_validate(user) for user in users]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving users: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving users")

@router.put("/{user_id}", response_model=UserOut, summary="Update user")
async def update_existing_user(
    user_id: int,
    user_update: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserOut:
    try:
        has_permission = await check_permissions([Permission.MANAGE_USERS.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update users")

        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        update_data = user_update.model_dump(exclude_none=True)
        if "email" in update_data and update_data["email"] != user.email:
            query = select(Users).where(Users.email == update_data["email"], Users.is_active == True)
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

        for key, value in update_data.items():
            setattr(user, key, value)

        user.updated_at = datetime.now(timezone.utc)
        db.add(user)
        await db.commit()
        await db.refresh(user)

        logger.info(f"User updated, user_id: {user_id}")
        return UserOut.model_validate(user)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating user")

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete user")
async def delete_existing_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> None:
    try:
        has_permission = await check_permissions([Permission.MANAGE_USERS.value], current_user, db)
        if not has_permission and not await is_admin_or_hr(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete users")

        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        user.is_active = False
        user.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"User soft deleted, user_id: {user_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting user")