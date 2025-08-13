from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone, timedelta
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
from app.core.permissions import get_user_permissions
from app.models.roles import Roles
from app.models.user_roles import UserRoles
from app.schemas.user_role import UserProfile
from slowapi import Limiter
from slowapi.util import get_remote_address
import logging

logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/auth", tags=["Authentication"])

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800  # Access token expiry reduced to 30 minutes
    model_config = ConfigDict(from_attributes=True)

class RefreshTokenRequest(BaseModel):
    refresh_token: str
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
    except Exception as e:
        logger.error(f"Failed to log system action: {str(e)}")

@router.post("/token", response_model=Token, status_code=status.HTTP_200_OK, summary="User login")
@limiter.limit("5/minute")
async def login_for_access_token(
    request: Request,
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
            
        access_token = create_access_token(
            {"sub": str(user.user_id)}, 
            expires_delta=timedelta(seconds=1800)  # 30 minutes
        )
        refresh_token = create_refresh_token(
            {"sub": str(user.user_id)}, 
            expires_delta=timedelta(seconds=604800)  # 7 days
        )

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
            logger.warning("Invalid refresh token provided")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Verify token issuance time to prevent reuse of old tokens
        issued_at = payload.get("iat")
        if not issued_at or (datetime.now(timezone.utc).timestamp() - issued_at > 604800):  # 7 days expiry
            logger.warning(f"Expired refresh token for user_id: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired",
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

        access_token = create_access_token(
            {"sub": str(user.user_id)}, 
            expires_delta=timedelta(seconds=1800)  # 30 minutes
        )
        new_refresh_token = create_refresh_token(
            {"sub": str(user.user_id)}, 
            expires_delta=timedelta(seconds=604800)  # 7 days
        )

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
        await db.commit()
        
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
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> UserProfile:
    """Retrieve profile information for the current user."""
    try:
        # Get user permissions
        user_permissions = await get_user_permissions(current_user.user_id, db)
        permissions_list = user_permissions
        
        # Get user roles
        roles_query = select(Roles.role_name).join(UserRoles).where(
            UserRoles.user_id == current_user.user_id,
            UserRoles.is_active == True
        )
        roles_result = await db.execute(roles_query)
        roles_list = [role[0] for role in roles_result.fetchall()]
        
        return UserProfile(
            user_id=current_user.user_id,
            email=current_user.email,
            first_name=current_user.first_name,
            last_name=current_user.last_name,
            job_title=current_user.job_title,
            roles=roles_list,
            permissions=permissions_list
        )

    except Exception as e:
        logger.error(f"Error retrieving user profile for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user profile"
        )

@router.post("/validate-token", status_code=status.HTTP_200_OK, summary="Validate access token")
async def validate_token(
    current_user: Users = Depends(get_current_active_user)
):
    """Validate if the current access token is valid and user is active."""
    try:
        return {
            "valid": True,
            "user_id": current_user.user_id,
            "email": current_user.email
        }
    except Exception as e:
        logger.error(f"Error validating token for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token validation failed"
        )