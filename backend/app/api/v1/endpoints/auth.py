from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user, oauth2_scheme
from app.core.config import Settings, get_settings
from app.core.permissions import require_permissions_dependency
from app.core.enums import Permission
from app.services.auth_service import (
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
    request_id = request.state.request_id
    return await login_user(
        request=request,
        credentials={"username": form_data.username, "password": form_data.password},
        db=db,
        settings=settings,
        request_id=request_id
    )

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
    settings: Settings = Depends(get_settings),
    _=Depends(require_permissions_dependency([Permission.REFRESH_TOKEN]))
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
    request_id = request.state.request_id
    return await refresh_token(
        request=request,
        token_request=token_request.dict(),
        db=db,
        settings=settings,
        request_id=request_id
    )

@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="User logout",
    description="Log out current user."
)
async def logout_endpoint(
    request: Request,
    current_user: Users = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> dict:
    """Handle user logout.

    Args:
        request: The incoming HTTP request.
        current_user: The authenticated user.
        token: The JWT token.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        dict: Logout confirmation message.
    """
    request_id = request.state.request_id
    await logout_user(
        request=request,
        user=current_user,
        token=token,
        db=db,
        settings=settings,
        request_id=request_id
    )
    return {"message": "Successfully logged out"}

@router.get(
    "/me",
    response_model=UserProfile,
    summary="Get current user profile",
    description="Retrieve profile information for the current user."
)
async def get_profile_endpoint(
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UserProfile:
    """Retrieve current user profile.

    Args:
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        UserProfile: User profile data.
    """
    request_id = request.state.request_id
    return await get_current_user_profile(
        user=current_user,
        db=db,
        request_id=request_id
    )

@router.post(
    "/validate-token",
    status_code=status.HTTP_200_OK,
    summary="Validate access token",
    description="Validate if the current access token is valid and user is active."
)
async def validate_token_endpoint(
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permissions_dependency([Permission.VIEW_OWN_PROFILE]))
) -> dict:
    """Validate access token.

    Args:
        request: The incoming HTTP request.
        current_user: The authenticated user.
        db: Database session dependency.

    Returns:
        dict: Token validation result.
    """
    request_id = request.state.request_id
    return await validate_token(
        user=current_user,
        db=db,
        request_id=request_id
    )