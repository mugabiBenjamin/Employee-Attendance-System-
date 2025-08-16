from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_active_user, oauth2_scheme
from app.services.auth_service import login_for_access_token, refresh_access_token, logout, get_current_user_profile, validate_token
from app.core.config import Settings, get_settings
import logging

from backend.app.schemas.user_role import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800  # Access token expiry (30 minutes)
    model_config = ConfigDict(from_attributes=True)

class RefreshTokenRequest(BaseModel):
    refresh_token: str
    model_config = ConfigDict(from_attributes=True)

@router.post("/token", 
            response_model=Token, 
            status_code=status.HTTP_200_OK, 
            summary="User login", 
            description="Authenticate user with email and password to get JWT tokens.")
async def login_endpoint(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> Token:
    """
    Handle user login by delegating to auth_service.
    """
    return await login_for_access_token(form_data, db, settings)

@router.post("/refresh", 
             response_model=Token, 
             status_code=status.HTTP_200_OK, 
             summary="Refresh access token", 
             description="Generate new access token using a valid refresh token.")
async def refresh_token_endpoint(
    request: Request,
    token_request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> Token:
    """
    Handle token refresh by delegating to auth_service.
    """
    return await refresh_access_token(token_request, db, settings)

@router.post("/logout", 
             status_code=status.HTTP_200_OK, 
             summary="User logout", 
             description="Log out current user and blacklist tokens.")
async def logout_endpoint(
    current_user: Users = Depends(get_current_active_user),
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    """
    Handle user logout by delegating to auth_service.
    """
    await logout(current_user, token, db)
    return {"message": "Successfully logged out"}

@router.get("/me", 
            response_model=UserProfile, 
            summary="Get current user profile", 
            description="Retrieve profile information for the current user.")
async def get_profile_endpoint(
    current_user: Users = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> UserProfile:
    """
    Retrieve current user profile by delegating to auth_service.
    """
    return await get_current_user_profile(current_user, db)

@router.post("/validate-token", 
            status_code=status.HTTP_200_OK, 
            summary="Validate access token", 
            description="Validate if the current access token is valid and user is active.")
async def validate_token_endpoint(
    current_user: Users = Depends(get_current_active_user)
):
    """
    Validate access token by delegating to auth_service.
    """
    return await validate_token(current_user)