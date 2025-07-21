from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.schemas.user import UserCreate, UserUpdate, UserOut
from app.services.user_service import create_user, update_user, delete_user, get_user_by_id, get_users
from app.api.deps import get_db_session, get_current_active_user, get_current_admin_user
from app.models.user import User
from app.core.config import settings

router = APIRouter()

@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_new_user(
    user: UserCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_admin_user)
):
    return await create_user(db, user)

@router.get("/{user_id}", response_model=UserOut)
async def read_user(
    user_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    if current_user.user_id != user_id and not await is_admin(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this user")
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserOut.model_validate(user)

@router.get("/", response_model=List[UserOut])
async def read_users(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_admin_user)
):
    return await get_users(db, skip, limit)

@router.put("/{user_id}", response_model=UserOut)
async def update_existing_user(
    user_id: int,
    user_update: UserUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_admin_user)
):
    return await update_user(db, user_id, user_update)

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_user(
    user_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_admin_user)
):
    await delete_user(db, user_id)
    return None

async def is_admin(db: AsyncSession, user: User) -> bool:
    from sqlmodel import select
    from app.models.user import User
    from app.models.user import user_roles, roles
    query = select(User).join(user_roles).join(roles).where(
        User.user_id == user.user_id,
        roles.role_name.in_(["Admin", "Super_Admin"])
    )
    result = await db.execute(query)
    return result.scalar_one_or_none() is not None