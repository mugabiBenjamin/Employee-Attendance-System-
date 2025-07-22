from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.schemas.user import UserCreate, UserUpdate, UserOut
from app.services.user_service import create_user, update_user, delete_user, get_user_by_id, get_users
from app.api.deps import get_db_session, get_current_active_user, get_current_admin_user
from app.models.user import User
from app.models.roles import UserRoles, Role
from app.core.config import settings

async def is_admin(db: AsyncSession, user: User) -> bool:
    from sqlmodel import select
    query = select(User).join(UserRoles).join(Role).where(
        User.user_id == user.user_id,
        Role.role_name.in_(["Admin", "Super_Admin"])
    )
    result = await db.execute(query)
    return result.scalar_one_or_none() is not None

router = APIRouter()

@router.post("/", 
    response_model=UserOut, 
    status_code=status.HTTP_201_CREATED,
    summary="Create new user",
    description="Create a new user account. Admin access required."
)
async def create_new_user(
    user: UserCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_admin_user)
):
    """Create a new user in the system."""
    return await create_user(db, user)

@router.get("/{user_id}", 
    response_model=UserOut,
    summary="Get user by ID",
    description="Retrieve user details. Users can view their own profile, admins can view any user."
)
async def read_user(
    user_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific user by their ID."""
    if current_user.user_id != user_id and not await is_admin(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this user")
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserOut.model_validate(user)

@router.get("/", 
    response_model=List[UserOut],
    summary="List all users",
    description="Retrieve all users with pagination. Admin access required."
)
async def read_users(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_admin_user)
):
    """Get a paginated list of all users."""
    return await get_users(db, skip, limit)

@router.put("/{user_id}", 
    response_model=UserOut,
    summary="Update user",
    description="Update user information. Admin access required."
)
async def update_existing_user(
    user_id: int,
    user_update: UserUpdate,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_admin_user)
):
    """Update an existing user's information."""
    return await update_user(db, user_id, user_update)

@router.delete("/{user_id}", 
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Delete a user account. Admin access required."
)
async def delete_existing_user(
    user_id: int,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_admin_user)
):
    """Delete a user from the system."""
    await delete_user(db, user_id)
    return None