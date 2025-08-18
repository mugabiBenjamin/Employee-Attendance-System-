from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user, oauth2_scheme
from app.core.config import Settings, get_settings
from app.services.auth_service import  ( 
    login_user, 
    logout_user, 
    refresh_token, 
    get_current_user_profile, 
    validate_token
)
from app.schemas.auth_schema import Token, RefreshTokenRequest, UserProfile
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post(
    "/token",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="User login",
    description="Authenticate user with email and password to get JWT tokens."
)
async def login_endpoint(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> Token:
    """Handle user login.

    Args:
        request: The incoming HTTP request.
        form_data: OAuth2 form data with username (email) and password.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        Token: JWT access and refresh tokens.
    """
    return await login_user({"username": form_data.username, "password": form_data.password}, request, db, settings)

@router.post(
    "/refresh",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description="Generate new access token using a valid refresh token."
)
async def refresh_token_endpoint(
    request: Request,
    token_request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> Token:
    """Handle token refresh.

    Args:
        request: The incoming HTTP request.
        token_request: Refresh token data.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        Token: New JWT access and refresh tokens.
    """
    return await refresh_token(token_request.dict(), request, db, settings)

@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="User logout",
    description="Log out current user."
)
async def logout_endpoint(
    current_user: Users = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Handle user logout.

    Args:
        current_user: The authenticated user.
        token: The JWT token to blacklist.
        db: Database session dependency.

    Returns:
        dict: Logout confirmation message.
    """
    await logout_user(current_user, token, db)
    return {"message": "Successfully logged out"}

@router.get(
    "/me",
    response_model=UserProfile,
    summary="Get current user profile",
    description="Retrieve profile information for the current user."
)
async def get_profile_endpoint(
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UserProfile:
    """Retrieve current user profile.

    Args:
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        UserProfile: User profile data.
    """
    return await get_current_user_profile(current_user, db)

@router.post(
    "/validate-token",
    status_code=status.HTTP_200_OK,
    summary="Validate access token",
    description="Validate if the current access token is valid and user is active."
)
async def validate_token_endpoint(
    current_user: Users = Depends(get_current_user)
) -> dict:
    """Validate access token.

    Args:
        current_user: The authenticated user.

    Returns:
        dict: Token validation result.
    """
    return await validate_token(current_user)