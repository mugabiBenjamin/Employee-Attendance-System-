from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, status
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlmodel import select
from app.core.security import verify_password, get_password_hash, create_access_token, create_refresh_token
from app.models.user import User
from app.models.user_roles import UserRole
from backend.app.models.user_roles import Role
from app.schemas.user import UserAuth, Token, UserCreate, UserOut
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

async def create_user(db: AsyncSession, user_create: UserCreate) -> UserOut:
    try:
        # Check for existing email
        query = select(User).where(User.email == user_create.email)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        
        # Validate employee_type
        valid_employee_types = ["full_time", "part_time", "contract", "intern", "temporary"]
        if user_create.employee_type not in valid_employee_types:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"Invalid employee type. Must be one of {valid_employee_types}")
        
        # Generate employee_id using sequence with func.lpad
        query = select(func.nextval('employee_id_seq'))
        result = await db.execute(query)
        sequence_value = result.scalar_one()
        employee_id = f"EMP{func.lpad(sequence_value, 6, '0')}"
        
        hashed_password = get_password_hash(user_create.password)
        db_user = User(
            **user_create.model_dump(exclude={"password"}, exclude_none=True),
            password_hash=hashed_password,
            employee_id=employee_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        
        # Assign default Employee role
        query = select(Role).where(Role.role_name == "Employee")
        result = await db.execute(query)
        role = result.scalar_one_or_none()
        if role:
            user_role = UserRole(
                user_id=db_user.user_id,
                role_id=role.role_id,
                assigned_at=datetime.now(timezone.utc),
                is_active=True
            )
            db.add(user_role)
            await db.commit()
        
        logger.info(f"User created, user_id {db_user.user_id}, employee_id {db_user.employee_id}")
        return UserOut.model_validate(db_user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error creating user")

async def check_user_permission(db: AsyncSession, user_id: int, required_permission: str) -> bool:
    try:
        # Validate permission key against defined permissions
        if required_permission not in settings.PERMISSION_KEYS:
            logger.warning(f"Invalid permission requested: {required_permission}")
            return False
            
        query = select(Role.permissions).join(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.is_active == True,
            Role.role_id == UserRole.role_id
        )
        result = await db.execute(query)
        
        # Collect all permissions from user's active roles
        permissions = []
        for role_perms in result.scalars().all():
            if isinstance(role_perms, dict):
                permissions.extend([k for k, v in role_perms.items() if v is True])
        
        # Check for super admin access or specific permission
        if "all_permissions" in permissions:
            return True
        return required_permission in permissions
    except Exception as e:
        logger.error(f"Error checking user permissions: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error checking permissions")