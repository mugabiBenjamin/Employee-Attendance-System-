from typing import Optional
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import InvalidRequestError
from datetime import datetime, timezone
from jose import JWTError, jwt
from app.models.users import Users
from app.schemas.system_log import SystemLogCreate
from app.services.system_log_service import create_system_log
from app.core.security import get_current_user, verify_password, create_access_token, create_refresh_token
from app.core.config import Settings, get_settings
from app.core.enums import SystemAction, Permission
from app.core.exceptions import AuthenticationError, ValidationError
from app.core.database import get_db, validate_enum_value
from app.core.permissions import require_permissions_dependency, invalidate_user_cache
from app.core.utils import get_request_id
import logging

logger = logging.getLogger(__name__)

async def login_user(
    request: Request,
    credentials: dict,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id)
) -> dict:
    """Authenticate user and generate tokens, logging the login action."""
    try:
        if not credentials.get("username") or not credentials.get("password"):
            raise ValidationError(detail="Email and password are required")

        query = select(Users).where(
            Users.email == credentials["username"],
            Users.is_active.is_(True),
            Users.deleted_at.is_(None)
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if user:
            logger.info(f"User found: {user.email}, employee_type: {user.employee_type}")

        if not user or not verify_password(credentials["password"], user.password_hash):
            raise AuthenticationError(detail="Invalid email or password")

        user.last_login = datetime.now(timezone.utc)
        db.add(user)

        access_token = create_access_token(data={"sub": str(user.user_id)})
        refresh_token = create_refresh_token(data={"sub": str(user.user_id)})

        # Validate SystemAction.LOGIN
        if not await validate_enum_value(SystemAction, SystemAction.LOGIN.value):
            logger.warning(f"Invalid SystemAction value: {SystemAction.LOGIN.value}")
            raise ValidationError(detail=f"Invalid system action: {SystemAction.LOGIN.value}")

        # Log the action
        log = SystemLogCreate(
            user_id=user.user_id,
            action=SystemAction.LOGIN,
            table_affected=None,
            record_id=None,
            old_values=None,
            new_values=None,
            ip_address=str(request.client.host),
            user_agent=request.headers.get("user-agent"),
            request_id=request_id
        )
        system_log = await create_system_log(log, request, user, db, settings, request_id)
        
        # Check if system_log is None
        if system_log is None:
            logger.error(
                f"Failed to create system log for login, user_id: {user.user_id}",
                extra={"request_id": request_id, "user_id": user.user_id}
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create system log for login"
            )

        try:
            cache_result = invalidate_user_cache(user.user_id)
            if cache_result is not None:
                await cache_result
            logger.info(f"Cache invalidated for user:{user.user_id}", extra={"request_id": request_id})
        except Exception as cache_error:
            logger.warning(f"Failed to invalidate cache for user:{user.user_id}: {str(cache_error)}", extra={"request_id": request_id})

        await db.commit()

        logger.info(f"User logged in, user_id: {user.user_id}", extra={"request_id": request_id, "user_id": user.user_id})
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }

    except ValidationError as e:
        logger.error(f"Validation error during login for email {credentials.get('username', 'unknown')}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except AuthenticationError:
        logger.error(f"Authentication error for email {credentials.get('username', 'unknown')}", extra={"request_id": request_id})
        raise
    except InvalidRequestError as e:
        logger.error(f"Mapper initialization error during login for email {credentials.get('username', 'unknown')}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database configuration error: Invalid model mapping"
        )
    except HTTPException as e:
        logger.error(f"HTTP error during login for email {credentials.get('username', 'unknown')}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error during login for email {credentials.get('username', 'unknown')}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing login"
        )

async def logout_user(
    request: Request,
    user: Users = Depends(get_current_user),
    token: str = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: Optional[str] = Depends(get_request_id)
) -> None:
    """Log user logout action."""
    try:
        # Validate SystemAction.LOGOUT
        if not await validate_enum_value(SystemAction, SystemAction.LOGOUT.value):
            logger.warning(f"Invalid SystemAction value: {SystemAction.LOGOUT.value}")
            raise ValidationError(detail=f"Invalid system action: {SystemAction.LOGOUT.value}")

        log = SystemLogCreate(
            user_id=user.user_id,
            action=SystemAction.LOGOUT,
            table_affected=None,
            record_id=None,
            old_values=None,
            new_values=None,
            ip_address=str(request.client.host),
            user_agent=request.headers.get("user-agent"),
            request_id=request_id
        )
        system_log = await create_system_log(log, request, user, db, settings, request_id)

        # Check if system_log is None
        if system_log is None:
            logger.error(
                f"Failed to create system log for logout, user_id: {user.user_id}",
                extra={"request_id": request_id, "user_id": user.user_id}
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create system log for logout"
            )

        logger.info(f"User logged out, user_id: {user.user_id}", extra={"request_id": request_id, "user_id": user.user_id})

    except ValidationError as e:
        logger.error(f"Validation error during logout for user_id {user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except InvalidRequestError as e:
        logger.error(f"Mapper initialization error during logout for user_id {user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database configuration error: Invalid model mapping"
        )
    except HTTPException as e:
        logger.error(f"HTTP error during logout for user_id {user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error during logout for user_id {user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing logout"
        )

async def refresh_token(
    request: Request,
    token_request: dict,
    db: AsyncSession,
    settings: Settings,
    request_id: Optional[str],
) -> dict:
    """Refresh access token using a valid refresh token."""
    try:
        if not token_request.get("refresh_token"):
            raise ValidationError(detail="Refresh token is required")

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

        if user:
            logger.info(f"User found: {user.email}, employee_type: {user.employee_type}")

        if not user:
            raise AuthenticationError(detail="User not found or inactive")

        access_token = create_access_token(data={"sub": str(user.user_id)})
        new_refresh_token = create_refresh_token(data={"sub": str(user.user_id)})

        # Validate SystemAction.TOKEN_REFRESH
        if not await validate_enum_value(SystemAction, SystemAction.TOKEN_REFRESH.value):
            logger.warning(f"Invalid SystemAction value: {SystemAction.TOKEN_REFRESH.value}")
            raise ValidationError(detail=f"Invalid system action: {SystemAction.TOKEN_REFRESH.value}")

        # Log the action
        log = SystemLogCreate(
            user_id=user.user_id,
            action=SystemAction.TOKEN_REFRESH,
            table_affected=None,
            record_id=None,
            old_values=None,
            new_values=None,
            ip_address=str(request.client.host),
            user_agent=request.headers.get("user-agent"),
            request_id=request_id
        )
        system_log = await create_system_log(log, request, user, db, settings, request_id)

        # Check if system_log is None
        if system_log is None:
            logger.error(
                f"Failed to create system log for token refresh, user_id: {user.user_id}",
                extra={"request_id": request_id, "user_id": user.user_id}
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create system log for token refresh"
            )

        logger.info(f"Token refreshed for user_id: {user.user_id}", extra={"request_id": request_id, "user_id": user.user_id})
        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }

    except ValidationError as e:
        logger.error(f"Validation error during token refresh: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except AuthenticationError:
        logger.error(f"Authentication error during token refresh", extra={"request_id": request_id})
        raise
    except JWTError:
        logger.error(f"JWT error during token refresh", extra={"request_id": request_id})
        raise AuthenticationError(detail="Invalid refresh token")
    except InvalidRequestError as e:
        logger.error(f"Mapper initialization error during token refresh for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database configuration error: Invalid model mapping"
        )
    except HTTPException as e:
        logger.error(f"HTTP error during token refresh for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error refreshing token for user_id {user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing token refresh"
        )

async def get_current_user_profile(
    user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_OWN_PROFILE]))
) -> dict:
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

    except InvalidRequestError as e:
        logger.error(f"Mapper initialization error retrieving profile for user_id {user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database configuration error: Invalid model mapping"
        )
    except Exception as e:
        logger.error(f"Error retrieving profile for user_id {user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving user profile"
        )

async def validate_token(
    user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: Optional[str] = Depends(get_request_id),
    _= Depends(require_permissions_dependency([Permission.VIEW_OWN_PROFILE]))
) -> dict:
    """Validate if the current access token is valid and user is active."""
    try:
        return {"message": f"Token is valid for user_id {user.user_id}"}

    except InvalidRequestError as e:
        logger.error(f"Mapper initialization error validating token for user_id {user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database configuration error: Invalid model mapping"
        )
    except Exception as e:
        logger.error(f"Error validating token for user_id {user.user_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error validating token"
        )