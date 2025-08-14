from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timezone
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_password_hash, get_current_active_user
from app.core.permissions import check_permissions
from app.core.config import settings
from app.core.enums import Permission
from app.schemas.user import UserCreate, UserUpdate, UserOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])

@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="Create new user")
async def create_new_user(
    user: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> UserOut:
    """Create a new user. Requires MANAGE_USERS permission."""
    try:
        # Check permissions using the refactored RBAC system
        await check_permissions([Permission.MANAGE_USERS], current_user, db)

        # Check if email already exists
        query = select(Users).where(Users.email == user.email, Users.is_active == True)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

        # Create new user
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
    """Get a user by ID. Requires MANAGE_USERS permission or viewing own profile."""
    try:
        # Allow users to view their own profile, otherwise require MANAGE_USERS permission
        if current_user.user_id != user_id:
            await check_permissions([Permission.MANAGE_USERS], current_user, db)

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
    """List all users. Requires MANAGE_USERS permission."""
    try:
        await check_permissions([Permission.MANAGE_USERS], current_user, db)

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
    """Update a user. Requires MANAGE_USERS permission or updating own profile (limited fields)."""
    try:
        # Check if user is updating their own profile
        is_self_update = current_user.user_id == user_id
        
        if not is_self_update:
            # Require MANAGE_USERS permission for updating other users
            await check_permissions([Permission.MANAGE_USERS], current_user, db)
        else:
            # For self-updates, restrict which fields can be modified
            restricted_fields = {'salary', 'employee_type', 'manager_id', 'is_active', 'hire_date'}
            update_data = user_update.model_dump(exclude_none=True)
            forbidden_fields = restricted_fields.intersection(update_data.keys())
            if forbidden_fields:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, 
                    detail=f"Cannot modify restricted fields: {', '.join(forbidden_fields)}"
                )

        # Get the user to update
        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Check email uniqueness if email is being updated
        update_data = user_update.model_dump(exclude_none=True)
        if "email" in update_data and update_data["email"] != user.email:
            query = select(Users).where(Users.email == update_data["email"], Users.is_active == True)
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

        # Apply updates
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
    """Soft delete a user. Requires MANAGE_USERS permission."""
    try:
        await check_permissions([Permission.MANAGE_USERS], current_user, db)

        # Prevent self-deletion
        if current_user.user_id == user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Cannot delete your own account"
            )

        query = select(Users).where(
            Users.user_id == user_id,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Soft delete
        user.is_active = False
        user.deleted_at = datetime.now(timezone.utc)
        user.updated_at = datetime.now(timezone.utc)
        
        await db.commit()

        logger.info(f"User soft deleted, user_id: {user_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting user")

@router.get("/me/profile", response_model=UserOut, summary="Get current user profile")
async def get_current_user_profile(
    current_user: Users = Depends(get_current_active_user)
) -> UserOut:
    """Get the current authenticated user's profile."""
    return UserOut.model_validate(current_user)