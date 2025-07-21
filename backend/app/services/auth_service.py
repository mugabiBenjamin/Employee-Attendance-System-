from datetime import datetime, timedelta
from typing import Optional
import uuid
from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.core.security import verify_password, get_password_hash, create_access_token, create_refresh_token
from app.models.user import User
from app.schemas.user import UserAuth, Token, UserCreate
from app.core.config import settings

async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    query = select(User).where(User.email == email, User.is_active == True, User.deleted_at == None)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return None
    return user

async def login_for_access_token(db: AsyncSession, user_auth: UserAuth) -> Token:
    user = await authenticate_user(db, user_auth.email, user_auth.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": str(user.user_id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh_token = create_refresh_token(data={"sub": str(user.user_id)})
    
    user.last_login = datetime.utcnow()
    await db.commit()
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token
    )

async def refresh_access_token(db: AsyncSession, refresh_token: str) -> Token:
    try:
        payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    
    query = select(User).where(User.user_id == user_id, User.is_active == True, User.deleted_at == None)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    access_token = create_access_token(data={"sub": str(user.user_id)})
    new_refresh_token = create_refresh_token(data={"sub": str(user.user_id)})
    
    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token
    )

async def create_user(db: AsyncSession, user_create: UserCreate) -> User:
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
    return db_user