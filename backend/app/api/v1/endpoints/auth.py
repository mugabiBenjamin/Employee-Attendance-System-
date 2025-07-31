from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone
from app.core.database import get_db
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.core.security import (
    create_access_token, 
    create_refresh_token, 
    verify_password, 
    decode_refresh_token,
    get_current_active_user
)
from app.core.enums import SystemAction
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600  # Access token expiry in seconds
    model_config = ConfigDict(from_attributes=True)

class RefreshTokenRequest(BaseModel):
    refresh_token: str
    model_config = ConfigDict(from_attributes=True)

class UserProfile(BaseModel):
    user_id: int
    email: str
    first_name: str
    last_name: str
    job_title: str | None  # Allow None to match database schema
    model_config = ConfigDict(from_attributes=True)

async def log_system_action(db: AsyncSession, user_id: int, action: SystemAction, details: str = None):
    """Helper to log system actions"""
    try:
        log_entry = SystemLogs(
            user_id=user_id,
            action=action.value,
            details=details,
            timestamp=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(log_entry)
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to log system action: {str(e)}")

@router.post("/token", response_model=Token, status_code=status.HTTP_200_OK, summary="User login")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: AsyncSession = Depends(get_db)
) -> Token:
    """Authenticate user with email and password to get JWT tokens."""
    try:
        if not form_data.username or not form_data.password:
            logger.warning("Missing credentials in login attempt")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email and password are required"
            )

        # Find active user by email
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

        # Create tokens
        access_token = create_access_token({"sub": str(user.user_id)})
        refresh_token = create_refresh_token({"sub": str(user.user_id)})

        # Log successful login
        await log_system_action(db, user.user_id, SystemAction.LOGIN, f"Successful login from {form_data.username}")

        logger.info(f"Successful login for user_id: {user.user_id}")
        return Token(access_token=access_token, refresh_token=refresh_token)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login for email {form_data.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed"
        )

@router.post("/refresh", response_model=Token, status_code=status.HTTP_200_OK, summary="Refresh access token")
async def refresh_access_token(
    token_request: RefreshTokenRequest, 
    db: AsyncSession = Depends(get_db)
) -> Token:
    """Generate new access token using a valid refresh token."""
    try:
        payload = decode_refresh_token(token_request.refresh_token)
        user_id = payload.get("sub")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Verify user still exists and is active
        query = select(Users).where(
            Users.user_id == int(user_id),
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            logger.warning(f"Refresh token used for inactive/deleted user_id: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account not found or inactive",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Create new tokens
        access_token = create_access_token({"sub": str(user.user_id)})
        new_refresh_token = create_refresh_token({"sub": str(user.user_id)})

        logger.info(f"Token refreshed for user_id: {user.user_id}")
        return Token(access_token=access_token, refresh_token=new_refresh_token)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token refresh failed"
        )

@router.post("/logout", status_code=status.HTTP_200_OK, summary="User logout")
async def logout(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Log out current user and record logout action."""
    try:
        # Log logout action
        await log_system_action(db, current_user.user_id, SystemAction.LOGOUT, "User logged out")
        
        logger.info(f"User logged out, user_id: {current_user.user_id}")
        return {"message": "Successfully logged out"}

    except Exception as e:
        logger.error(f"Error during logout for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )

@router.get("/me", response_model=UserProfile, summary="Get current user profile")
async def get_current_user_profile(
    current_user: Users = Depends(get_current_active_user)
) -> UserProfile:
    """Get the current authenticated user's profile information."""
    return UserProfile(
        user_id=current_user.user_id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        job_title=current_user.job_title
    )

@router.post("/validate-token", status_code=status.HTTP_200_OK, summary="Validate access token")
async def validate_token(
    current_user: Users = Depends(get_current_active_user)
):
    """Validate if the current access token is valid and user is active."""
    return {
        "valid": True,
        "user_id": current_user.user_id,
        "email": current_user.email
    }