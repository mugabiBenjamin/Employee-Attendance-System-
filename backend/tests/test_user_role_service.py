from fastapi import HTTPException
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from app.core.database import AsyncSessionLocal
from app.models.users import Users
from app.models.roles import Roles
from app.models.user_roles import UserRoles
from app.models.system_logs import SystemLogs
from app.services.user_role_service import (
    create_user_role,
    get_user_role_by_id,
    get_user_roles,
    update_user_role,
    delete_user_role,
)
from app.core.config import settings
from app.core.enums import SystemAction
from pydantic import BaseModel, ConfigDict

# Mock schemas for testing
class UserRoleCreateInternal(BaseModel):
    user_id: int
    role_id: int
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)

class UserRoleUpdateInternal(BaseModel):
    role_id: int | None = None
    is_active: bool | None = None

    model_config = ConfigDict(from_attributes=True)

class UserRoleOut(BaseModel):
    user_role_id: int
    user_id: int
    role_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    user = Users(
        email="test@example.com",
        password_hash="hashed_password",
        first_name="Test",
        last_name="User",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def test_role(db_session: AsyncSession):
    role = Roles(
        role_name="TestRole",
        description="Test Role Description",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)
    return role

@pytest_asyncio.fixture
async def test_user_role(db_session: AsyncSession, test_user: Users, test_role: Roles):
    user_role = UserRoles(
        user_id=test_user.user_id,
        role_id=test_role.role_id,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(user_role)
    await db_session.commit()
    await db_session.refresh(user_role)
    return user_role

@pytest.mark.asyncio
async def test_create_user_role_success(db_session: AsyncSession, test_user: Users, test_role: Roles):
    user_role_data = UserRoleCreateInternal(
        user_id=test_user.user_id,
        role_id=test_role.role_id,
        is_active=True
    )
    result = await create_user_role(db_session, user_role_data, test_user)
    assert result is not None
    assert result.user_id == test_user.user_id
    assert result.role_id == test_role.role_id
    assert result.is_active is True
    assert result.created_at is not None
    # Verify system log
    query = select(SystemLogs).where(SystemLogs.record_id == result.user_role_id)
    log_result = await db_session.execute(query)
    log = log_result.scalar_one_or_none()
    assert log is not None
    assert log.action == SystemAction.ASSIGN_ROLE
    assert log.table_affected == "user_roles"

@pytest.mark.asyncio
async def test_create_user_role_invalid_user(db_session: AsyncSession, test_role: Roles, test_user: Users):
    user_role_data = UserRoleCreateInternal(
        user_id=999,
        role_id=test_role.role_id,
        is_active=True
    )
    with pytest.raises(HTTPException) as exc:
        await create_user_role(db_session, user_role_data, test_user)
    assert exc.value.status_code == 404
    assert exc.value.detail == "User not found"

@pytest.mark.asyncio
async def test_create_user_role_invalid_role(db_session: AsyncSession, test_user: Users):
    user_role_data = UserRoleCreateInternal(
        user_id=test_user.user_id,
        role_id=999,
        is_active=True
    )
    with pytest.raises(HTTPException) as exc:
        await create_user_role(db_session, user_role_data, test_user)
    assert exc.value.status_code == 404
    assert exc.value.detail == "Role not found"

@pytest.mark.asyncio
async def test_create_user_role_already_assigned(db_session: AsyncSession, test_user: Users, test_role: Roles, test_user_role: UserRoles):
    user_role_data = UserRoleCreateInternal(
        user_id=test_user.user_id,
        role_id=test_role.role_id,
        is_active=True
    )
    with pytest.raises(HTTPException) as exc:
        await create_user_role(db_session, user_role_data, test_user)
    assert exc.value.status_code == 400
    assert exc.value.detail == "User is already assigned to this role"

@pytest.mark.asyncio
async def test_create_user_role_internal_error(db_session: AsyncSession, test_user: Users, test_role: Roles):
    user_role_data = UserRoleCreateInternal(
        user_id=test_user.user_id,
        role_id=test_role.role_id,
        is_active=True
    )
    with patch.object(db_session, "commit", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await create_user_role(db_session, user_role_data, test_user)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error creating user role assignment"

@pytest.mark.asyncio
async def test_get_user_role_by_id_success(db_session: AsyncSession, test_user_role: UserRoles):
    result = await get_user_role_by_id(db_session, test_user_role.user_role_id)
    assert result is not None
    assert result.user_role_id == test_user_role.user_role_id
    assert result.user_id == test_user_role.user_id
    assert result.role_id == test_user_role.role_id
    assert result.is_active == test_user_role.is_active

@pytest.mark.asyncio
async def test_get_user_role_by_id_not_found(db_session: AsyncSession):
    result = await get_user_role_by_id(db_session, 999)
    assert result is None

@pytest.mark.asyncio
async def test_get_user_role_by_id_internal_error(db_session: AsyncSession):
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await get_user_role_by_id(db_session, 1)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error retrieving user role assignment"

@pytest.mark.asyncio
async def test_get_user_roles_success(db_session: AsyncSession, test_user: Users, test_user_role: UserRoles):
    result = await get_user_roles(db_session, test_user.user_id, skip=0, limit=10)
    assert len(result) >= 1
    assert any(ur.user_role_id == test_user_role.user_role_id for ur in result)
    assert all(ur.user_id == test_user.user_id for ur in result)

@pytest.mark.asyncio
async def test_get_user_roles_invalid_user(db_session: AsyncSession):
    with pytest.raises(HTTPException) as exc:
        await get_user_roles(db_session, 999, skip=0, limit=10)
    assert exc.value.status_code == 404
    assert exc.value.detail == "User not found"

@pytest.mark.asyncio
async def test_get_user_roles_empty(db_session: AsyncSession, test_user: Users):
    result = await get_user_roles(db_session, test_user.user_id, skip=0, limit=10)
    assert len(result) == 0

@pytest.mark.asyncio
async def test_get_user_roles_internal_error(db_session: AsyncSession, test_user: Users):
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await get_user_roles(db_session, test_user.user_id, skip=0, limit=10)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error retrieving role assignments"

@pytest.mark.asyncio
async def test_update_user_role_success(db_session: AsyncSession, test_user: Users, test_user_role: UserRoles, test_role: Roles):
    new_role = Roles(
        role_name="NewRole",
        description="New Role Description",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(new_role)
    await db_session.commit()
    await db_session.refresh(new_role)

    update_data = UserRoleUpdateInternal(
        role_id=new_role.role_id,
        is_active=False
    )
    result = await update_user_role(db_session, test_user_role.user_role_id, update_data, test_user)
    assert result is not None
    assert result.user_role_id == test_user_role.user_role_id
    assert result.role_id == new_role.role_id
    assert result.is_active is False
    # Verify system log
    query = select(SystemLogs).where(SystemLogs.record_id == test_user_role.user_role_id, SystemLogs.action == SystemAction.UPDATE_ROLE_ASSIGNMENT)
    log_result = await db_session.execute(query)
    log = log_result.scalar_one_or_none()
    assert log is not None
    assert log.action == SystemAction.UPDATE_ROLE_ASSIGNMENT
    assert log.table_affected == "user_roles"

@pytest.mark.asyncio
async def test_update_user_role_invalid_role(db_session: AsyncSession, test_user: Users, test_user_role: UserRoles):
    update_data = UserRoleUpdateInternal(
        role_id=999
    )
    with pytest.raises(HTTPException) as exc:
        await update_user_role(db_session, test_user_role.user_role_id, update_data, test_user)
    assert exc.value.status_code == 404
    assert exc.value.detail == "Role not found"

@pytest.mark.asyncio
async def test_update_user_role_already_assigned(db_session: AsyncSession, test_user: Users, test_role: Roles, test_user_role: UserRoles):
    new_role = Roles(
        role_name="NewRole",
        description="New Role Description",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(new_role)
    await db_session.commit()
    await db_session.refresh(new_role)

    other_assignment = UserRoles(
        user_id=test_user.user_id,
        role_id=new_role.role_id,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(other_assignment)
    await db_session.commit()

    update_data = UserRoleUpdateInternal(
        role_id=new_role.role_id
    )
    with pytest.raises(HTTPException) as exc:
        await update_user_role(db_session, test_user_role.user_role_id, update_data, test_user)
    assert exc.value.status_code == 400
    assert exc.value.detail == "User is already assigned to this role"

@pytest.mark.asyncio
async def test_update_user_role_not_found(db_session: AsyncSession, test_user: Users):
    update_data = UserRoleUpdateInternal(
        is_active=False
    )
    with pytest.raises(HTTPException) as exc:
        await update_user_role(db_session, 999, update_data, test_user)
    assert exc.value.status_code == 404
    assert exc.value.detail == "User role assignment not found"

@pytest.mark.asyncio
async def test_update_user_role_internal_error(db_session: AsyncSession, test_user: Users, test_user_role: UserRoles):
    update_data = UserRoleUpdateInternal(
        is_active=False
    )
    with patch.object(db_session, "commit", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await update_user_role(db_session, test_user_role.user_role_id, update_data, test_user)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error updating user role assignment"

@pytest.mark.asyncio
async def test_delete_user_role_success(db_session: AsyncSession, test_user: Users, test_user_role: UserRoles):
    await delete_user_role(db_session, test_user_role.user_role_id, test_user)
    query = select(UserRoles).where(
        UserRoles.user_role_id == test_user_role.user_role_id,
        UserRoles.is_active == True
    )
    result = await db_session.execute(query)
    assert result.scalar_one_or_none() is None
    # Verify system log
    query = select(SystemLogs).where(
        SystemLogs.record_id == test_user_role.user_role_id,
        SystemLogs.action == SystemAction.DELETE_ROLE_ASSIGNMENT
    )
    log_result = await db_session.execute(query)
    log = log_result.scalar_one_or_none()
    assert log is not None
    assert log.action == SystemAction.DELETE_ROLE_ASSIGNMENT
    assert log.table_affected == "user_roles"

@pytest.mark.asyncio
async def test_delete_user_role_not_found(db_session: AsyncSession, test_user: Users):
    with pytest.raises(HTTPException) as exc:
        await delete_user_role(db_session, 999, test_user)
    assert exc.value.status_code == 404
    assert exc.value.detail == "User role assignment not found"

@pytest.mark.asyncio
async def test_delete_user_role_internal_error(db_session: AsyncSession, test_user: Users, test_user_role: UserRoles):
    with patch.object(db_session, "commit", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await delete_user_role(db_session, test_user_role.user_role_id, test_user)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error deleting user role assignment"