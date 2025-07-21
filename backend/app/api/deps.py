from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token")

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_db() as session:
        yield session

async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user

async def get_current_admin_user(current_user: User = Depends(get_current_active_user)) -> User:
    query = select(User).join(user_roles).join(roles).where(
        User.user_id == current_user.user_id,
        roles.role_name.in_(["Admin", "Super_Admin"])
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current_user

async def get_current_manager_user(current_user: User = Depends(get_current_active_user)) -> User:
    query = select(User).join(user_roles).join(roles).where(
        User.user_id == current_user.user_id,
        roles.role_name == "Manager"
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current_user

async def get_current_hr_user(current_user: User = Depends(get_current_active_user)) -> User:
    query = select(User).join(user_roles).join(roles).where(
        User.user_id == current_user.user_id,
        roles.role_name == "HR"
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current_user