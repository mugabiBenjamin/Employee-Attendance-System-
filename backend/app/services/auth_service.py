from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from jose import JWTError, jwt
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.core.security import verify_password, create_access_token, create_refresh_token
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import AuthenticationError
from app.core.database import get_db
from app.core.permissions import require_permissions
import logging

logger = logging.getLogger(__name__)

async def login_user(
    request: Request,
    credentials: dict,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> dict:
    """Authenticate user and generate tokens, logging the login action."""
    try:
        query = select(Users).where(
            Users.email == credentials["username"],
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user or not verify_password(credentials["password"], user.password_hash):
            raise AuthenticationError(detail="Invalid email or password")

        user.last_login = datetime.now(timezone.utc)
        db.add(user)

        access_token = create_access_token(data={"sub": str(user.user_id)})
        refresh_token = create_refresh_token(data={"sub": str(user.user_id)})

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
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }

    except AuthenticationError:
        raise
    except Exception as e:
        logger.error(f"Error during login for email {credentials['username']}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing login"
        )

async def logout_user(
    request: Request,
    user: Users,
    token: str,
    db: AsyncSession = Depends(get_db)
) -> None:
    """Log user logout action."""
    try:
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
    request: Request,
    token_request: dict,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(require_permissions([Permission.REFRESH_TOKEN]))
) -> dict:
    """Refresh access token using a valid refresh token."""
    try:
        payload = jwt.decode(token_request["refresh_token"], settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise AuthenticationError(detail="Invalid refresh token")

        query = select(Users).where(
            Users.user_id == int(user_id),
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            raise AuthenticationError(detail="User not found or inactive")

        access_token = create_access_token(data={"sub": str(user.user_id)})
        new_refresh_token = create_refresh_token(data={"sub": str(user.user_id)})

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
        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }

    except AuthenticationError:
        raise
    except JWTError:
        raise AuthenticationError(detail="Invalid refresh token")
    except Exception as e:
        logger.error(f"Error refreshing token for user_id {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing token refresh"
        )

async def get_current_user_profile(user: Users, db: AsyncSession = Depends(get_db)) -> dict:
    """Retrieve profile information for the current user."""
    try:
        return {
            "user_id": user.user_id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "employee_id": user.employee_id,
            "department_id": user.department_id,
            "is_active": user.is_active
        }

    except Exception as e:
        logger.error(f"Error retrieving profile for user_id {user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving user profile"
        )

async def validate_token(user: Users) -> dict:
    """Validate if the current access token is valid and user is active."""
    try:
        return {"message": f"Token is valid for user_id {user.user_id}"}

    except Exception as e:
        logger.error(f"Error validating token for user_id {user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error validating token"
        )