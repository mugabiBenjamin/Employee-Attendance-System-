from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from pydantic import BaseModel, EmailStr
from jose import JWTError, jwt
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.core.security import verify_password, create_access_token, create_refresh_token, get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import AuthenticationError
from app.core.database import get_db
from app.core.permissions import require_permissions
import logging

logger = logging.getLogger(__name__)

class LoginCredentials(BaseModel):
    email: EmailStr
    password: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

async def login_user(
    credentials: LoginCredentials,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> TokenResponse:
    """
    Authenticate user and generate access/refresh tokens, logging the login action.
    """
    try:
        # Find user by email
        query = select(Users).where(
            Users.email == credentials.email,
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user or not verify_password(credentials.password, user.password_hash):
            raise AuthenticationError(detail="Invalid email or password")

        # Update last login
        user.last_login = datetime.now(timezone.utc)
        db.add(user)

        # Generate tokens
        access_token = create_access_token(data={"sub": str(user.user_id)})
        refresh_token = create_refresh_token(data={"sub": str(user.user_id)})

        # Log login action
        system_log = SystemLogs(
            user_id=user.user_id,
            action=SystemAction.LOGIN,
            table_affected=None,
            record_id=None,
            old_values=None,
            new_values=None,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"User logged in, user_id: {user.user_id}")
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    except AuthenticationError:
        raise
    except Exception as e:
        logger.error(f"Error during login for email {credentials.email}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing login"
        )

async def logout_user(
    request: Request,
    user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> None:
    """
    Log user logout action.
    """
    try:
        # Log logout action
        system_log = SystemLogs(
            user_id=user.user_id,
            action=SystemAction.LOGOUT,
            table_affected=None,
            record_id=None,
            old_values=None,
            new_values=None,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"User logged out, user_id: {user.user_id}")

    except Exception as e:
        logger.error(f"Error during logout for user_id {user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing logout"
        )

async def refresh_token(
    token_request: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.REFRESH_TOKEN]))
) -> TokenResponse:
    """
    Refresh access token using a valid refresh token.
    """
    try:
        # Decode refresh token
        try:
            payload = jwt.decode(token_request.refresh_token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id: str = payload.get("sub")
            if user_id is None:
                raise AuthenticationError(detail="Invalid refresh token")
        except JWTError:
            raise AuthenticationError(detail="Invalid refresh token")

        # Verify user
        query = select(Users).where(
            Users.user_id == int(user_id),
            Users.is_active == True,
            Users.deleted_at == None
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            raise AuthenticationError(detail="User not found or inactive")

        # Generate new tokens
        access_token = create_access_token(data={"sub": str(user.user_id)})
        new_refresh_token = create_refresh_token(data={"sub": str(user.user_id)})

        # Log token refresh action
        system_log = SystemLogs(
            user_id=user.user_id,
            action=SystemAction.TOKEN_REFRESH,
            table_affected=None,
            record_id=None,
            old_values=None,
            new_values=None,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(system_log)
        await db.commit()

        logger.info(f"Token refreshed for user_id: {user.user_id}")
        return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)

    except AuthenticationError:
        raise
    except Exception as e:
        logger.error(f"Error refreshing token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing token refresh"
        )