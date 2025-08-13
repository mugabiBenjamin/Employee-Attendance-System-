from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.users import Users
from app.models.departments import Departments
from app.models.roles import Roles

async def validate_user_exists(db: AsyncSession, user_id: int) -> None:
    """Validate that a user exists and is active."""
    query = select(Users).where(
        Users.user_id == user_id,
        Users.is_active == True,
        Users.deleted_at == None
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

async def validate_department_exists(db: AsyncSession, department_id: int) -> None:
    """Validate that a department exists and is active."""
    query = select(Departments).where(
        Departments.department_id == department_id,
        Departments.is_active == True,
        Departments.deleted_at == None
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found"
        )

async def validate_role_exists(db: AsyncSession, role_id: int) -> None:
    """Validate that a role exists and is active."""
    query = select(Roles).where(
        Roles.role_id == role_id,
        Roles.is_active == True,
        Roles.deleted_at == None
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )