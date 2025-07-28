from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import AsyncGenerator, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone
from app.core.database import AsyncSessionLocal
from app.models.users import Users
from app.core.security import create_access_token, create_refresh_token, verify_password, decode_refresh_token
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

class Token(BaseModel):
    """Schema for JWT token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

    model_config = ConfigDict(from_attributes=True)

class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request."""
    refresh_token: str

async def get_db() -> AsyncGenerator[AsyncSession, None]:
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

@router.post("/token", response_model=Token, status_code=status.HTTP_200_OK, summary="User login", description="Authenticate user with email (as username) and password to get JWT tokens.")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)) -> Token:
    """Authenticate user credentials and return access and refresh tokens."""
    try:
        # Use form_data.username as email (OAuth2 standard)
        query = select(Users).where(
            Users.email == form_data.username,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user or not verify_password(form_data.password, user.password_hash):
            logger.warning(f"Failed login attempt for email: {form_data.username}")
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
        logger.error(f"Error during login for email {form_data.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during authentication"
        )

@router.post("/refresh", response_model=Token, status_code=status.HTTP_200_OK, summary="Refresh access token", description="Generate new access token using a valid refresh token.")
async def refresh_access_token(token_request: RefreshTokenRequest, db: AsyncSession = Depends(get_db)) -> Token:
    """Refresh an expired access token using a valid refresh token."""
    try:
        payload = decode_refresh_token(token_request.refresh_token)
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