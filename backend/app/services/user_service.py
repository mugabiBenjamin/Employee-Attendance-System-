from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserOut
from app.core.security import get_password_hash
import uuid

async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    query = select(User).where(User.user_id == user_id, User.is_active == True, User.deleted_at == None)
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    query = select(User).where(User.email == email, User.is_active == True, User.deleted_at == None)
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def create_user(db: AsyncSession, user_create: UserCreate) -> UserOut:
    query = select(User).where(User.email == user_create.email)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    
    hashed_password = get_password_hash(user_create.password)
    db_user = User(
        **user_create.dict(exclude={"password"}),
        password_hash=hashed_password,
        employee_id=f"EMP{str(uuid.uuid4())[:6].upper()}"
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return UserOut.from_orm(db_user)

async def update_user(db: AsyncSession, user_id: int, user_update: UserUpdate) -> UserOut:
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    update_data = user_update.dict(exclude_unset=True)
    if "password" in update_data:
        update_data["password_hash"] = get_password_hash(update_data.pop("password"))
    
    for key, value in update_data.items():
        setattr(user, key, value)
    
    user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)
    return UserOut.from_orm(user)

async def delete_user(db: AsyncSession, user_id: int) -> None:
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    user.is_active = False
    user.deleted_at = datetime.utcnow()
    await db.commit()

async def get_users(db: AsyncSession, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[UserOut]:
    query = select(User).where(User.is_active == True, User.deleted_at == None).offset(skip).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()
    return [UserOut.from_orm(user) for user in users]