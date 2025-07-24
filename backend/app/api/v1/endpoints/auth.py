from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr
from datetime import datetime, timezone
from app.core.database import AsyncSessionLocal
from app.models.users import Users
from app.core.security import create_access_token, create_refresh_token, verify_password, decode_refresh_token
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

class UserAuth(BaseModel):
    """Schema for user authentication credentials."""
    email: EmailStr
    password: str

    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    """Schema for JWT token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

    model_config = ConfigDict(from_attributes=True)

async def get_db() -> AsyncSession:
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

@router.post("/token", response_model=Token, status_code=status.HTTP_200_OK, summary="User login", description="Authenticate user and return JWT tokens.")
async def login_for_access_token(user_auth: UserAuth, db: AsyncSession = Depends(get_db)) -> Token:
    """
    Authenticate user credentials and return access and refresh tokens.

    Args:
        user_auth: User authentication credentials (email, password).
        db: Async database session.

    Returns:
        Token response containing access and refresh tokens.

    Raises:
        HTTPException: If credentials are invalid or user is not found/inactive.
    """
    try:
        query = select(Users).where(
            Users.email == user_auth.email,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user or not verify_password(user_auth.password, user.password_hash):
            logger.warning(f"Failed login attempt for email: {user_auth.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"}
            )

        access_token = create_access_token({"sub": str(user.user_id)})
        refresh_token = create_refresh_token({"sub": str(user.user_id)})

        logger.info(f"Successful login for user_id: {user.user_id}")
        return Token(access_token=access_token, refresh_token=refresh_token)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login for email {user_auth.email}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during authentication"
        )

@router.post("/refresh", response_model=Token, status_code=status.HTTP_200_OK, summary="Refresh access token", description="Generate new access token using a valid refresh token.")
async def refresh_access_token(refresh_token: str, db: AsyncSession = Depends(get_db)) -> Token:
    """
    Refresh an expired access token using a valid refresh token.

    Args:
        refresh_token: The refresh token provided by the client.
        db: Async database session.

    Returns:
        Token response containing new access and refresh tokens.

    Raises:
        HTTPException: If refresh token is invalid or user is not found/inactive.
    """
    try:
        payload = decode_refresh_token(refresh_token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"}
            )

        query = select(Users).where(
            Users.user_id == int(user_id),
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            logger.warning(f"Invalid refresh token for user_id: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
                headers={"WWW-Authenticate": "Bearer"}
            )

        access_token = create_access_token({"sub": str(user.user_id)})
        new_refresh_token = create_refresh_token({"sub": str(user.user_id)})

        logger.info(f"Refresh token issued for user_id: {user.user_id}")
        return Token(access_token=access_token, refresh_token=new_refresh_token)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during token refresh"
        )