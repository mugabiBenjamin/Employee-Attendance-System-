from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.models.users import Users
from app.core.database import get_db, redis
import logging

logger = logging.getLogger(__name__)

# Configure bcrypt with configurable rounds from environment (minimum 12 for security)
settings = get_settings()
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=max(12, settings.BCRYPT_ROUNDS)
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password using bcrypt."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Error verifying password: {str(e)}")
        return False

def get_password_hash(password: str) -> str:
    """Generate a hashed password using bcrypt with configured rounds."""
    try:
        return pwd_context.hash(password)
    except Exception as e:
        logger.error(f"Error hashing password: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error hashing password"
        )

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token with configurable expiry."""
    try:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (
            expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        logger.debug(f"Access token created for user_id: {to_encode.get('sub')}")
        return encoded_jwt
    except Exception as e:
        logger.error(f"Error creating access token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating access token"
        )

def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT refresh token with configurable expiry."""
    try:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (
            expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        )
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        logger.debug(f"Refresh token created for user_id: {to_encode.get('sub')}")
        return encoded_jwt
    except Exception as e:
        logger.error(f"Error creating refresh token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating refresh token"
        )

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Users:
    """Retrieve the current user from a JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        if await is_token_blacklisted(token):
            logger.warning("Attempted use of blacklisted token")
            raise credentials_exception

        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id_str = payload.get("sub")
        if user_id_str is None:
            logger.warning("Token missing 'sub' claim")
            raise credentials_exception
        user_id = int(user_id_str)
    except (JWTError, ValueError, TypeError) as e:
        logger.warning(f"Invalid token: {str(e)}")
        raise credentials_exception

    query = select(Users).where(
        Users.user_id == user_id,
        Users.is_active == True,
        Users.deleted_at.is_(None)
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if user is None:
        logger.warning(f"User not found for user_id: {user_id}")
        raise credentials_exception
    logger.debug(f"User authenticated: {user_id}")
    return user

async def get_current_active_user(current_user: Users = Depends(get_current_user)) -> Users:
    """Ensure the current user is active."""
    if not current_user.is_active:
        logger.warning(f"Inactive user attempted access: {current_user.user_id}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    return current_user

def decode_refresh_token(refresh_token: str) -> dict:
    """Decode a refresh token with signature verification."""
    try:
        payload = jwt.decode(refresh_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        logger.debug(f"Refresh token decoded for user_id: {payload.get('sub')}")
        return payload
    except JWTError as e:
        logger.warning(f"Invalid refresh token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"}
        )

def decode_access_token(token: str) -> dict:
    """Decode an access token with signature verification."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        logger.debug(f"Access token decoded for user_id: {payload.get('sub')}")
        return payload
    except JWTError as e:
        logger.warning(f"Invalid access token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"}
        )

async def blacklist_token(token: str, expires_at: float) -> None:
    """Add a token to the Redis blacklist with TTL based on its expiry."""
    try:
        if redis:
            ttl = max(1, int(expires_at - datetime.now(timezone.utc).timestamp()))
            await redis.setex(f"blacklist:{token}", ttl, "1")
            logger.debug(f"Token blacklisted with TTL {ttl}s")
        else:
            logger.warning("Redis not available, token not blacklisted")
    except Exception as e:
        logger.error(f"Error blacklisting token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error blacklisting token"
        )

async def is_token_blacklisted(token: str) -> bool:
    """Check if a token is blacklisted in Redis."""
    try:
        if redis:
            is_blacklisted = await redis.exists(f"blacklist:{token}")
            logger.debug(f"Token blacklist check: {'blacklisted' if is_blacklisted else 'not blacklisted'}")
            return bool(is_blacklisted)
        logger.debug("Redis not available, assuming token is not blacklisted")
        return False
    except Exception as e:
        logger.error(f"Error checking token blacklist: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error checking token blacklist"
        )