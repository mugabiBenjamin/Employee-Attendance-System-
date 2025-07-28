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
from app.models.system_logs import SystemLogs
from app.services.user_service import create_user, get_user_by_id, get_users, update_user, delete_user
from app.core.config import settings
from app.core.enums import SystemAction
from pydantic import BaseModel, ConfigDict

# Mock schemas for testing
class UserCreate(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str
    phone_number: str | None = None
    job_title: str | None = None

    model_config = ConfigDict(from_attributes=True)

class UserUpdate(BaseModel):
    email: str | None = None
    password: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone_number: str | None = None
    job_title: str | None = None
    is_active: bool | None = None

    model_config = ConfigDict(from_attributes=True)

class UserOut(BaseModel):
    user_id: int
    email: str
    first_name: str
    last_name: str
    phone_number: str | None
    job_title: str | None
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
        phone_number="1234567890",
        job_title="Tester",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def current_user(db_session: AsyncSession):
    user = Users(
        email="admin@example.com",
        password_hash="hashed_admin_password",
        first_name="Admin",
        last_name="User",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest.mark.asyncio
async def test_create_user_success(db_session: AsyncSession, current_user: Users):
    with patch("app.core.security.get_password_hash", return_value="hashed_new_password"):
        user_data = UserCreate(
            email="newuser@example.com",
            password="NewPassword123",
            first_name="New",
            last_name="User",
            phone_number="0987654321",
            job_title="Developer"
        )
        result = await create_user(db_session, user_data, current_user)
        assert result is not None
        assert result.email == "newuser@example.com"
        assert result.first_name == "New"
        assert result.last_name == "User"
        assert result.phone_number == "0987654321"
        assert result.job_title == "Developer"
        assert result.is_active is True
        assert result.created_at is not None
        # Verify system log
        query = select(SystemLogs).where(SystemLogs.record_id == result.user_id)
        log_result = await db_session.execute(query)
        log = log_result.scalar_one_or_none()
        assert log is not None
        assert log.action == SystemAction.USER_CREATED
        assert log.table_affected == "users"

@pytest.mark.asyncio
async def test_create_user_duplicate_email(db_session: AsyncSession, test_user: Users, current_user: Users):
    user_data = UserCreate(
        email="test@example.com",
        password="NewPassword123",
        first_name="New",
        last_name="User"
    )
    with pytest.raises(HTTPException) as exc:
        await create_user(db_session, user_data, current_user)
    assert exc.value.status_code == 400
    assert exc.value.detail == "Email already registered"

@pytest.mark.asyncio
async def test_create_user_internal_error(db_session: AsyncSession, current_user: Users):
    user_data = UserCreate(
        email="newuser@example.com",
        password="NewPassword123",
        first_name="New",
        last_name="User"
    )
    with patch.object(db_session, "commit", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await create_user(db_session, user_data, current_user)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error creating user"

@pytest.mark.asyncio
async def test_get_user_by_id_success(db_session: AsyncSession, test_user: Users):
    result = await get_user_by_id(db_session, test_user.user_id)
    assert result is not None
    assert result.user_id == test_user.user_id
    assert result.email == test_user.email
    assert result.first_name == test_user.first_name
    assert result.last_name == test_user.last_name
    assert result.phone_number == test_user.phone_number
    assert result.job_title == test_user.job_title
    assert result.is_active == test_user.is_active

@pytest.mark.asyncio
async def test_get_user_by_id_not_found(db_session: AsyncSession):
    result = await get_user_by_id(db_session, 999)
    assert result is None

@pytest.mark.asyncio
async def test_get_user_by_id_internal_error(db_session: AsyncSession):
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await get_user_by_id(db_session, 1)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error retrieving user"

@pytest.mark.asyncio
async def test_get_users_success(db_session: AsyncSession, test_user: Users):
    result = await get_users(db_session, skip=0, limit=10)
    assert len(result) >= 1
    assert any(u.user_id == test_user.user_id for u in result)
    assert all(u.is_active is True for u in result)

@pytest.mark.asyncio
async def test_get_users_empty(db_session: AsyncSession):
    result = await get_users(db_session, skip=0, limit=10)
    assert len(result) == 0

@pytest.mark.asyncio
async def test_get_users_internal_error(db_session: AsyncSession):
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await get_users(db_session, skip=0, limit=10)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error retrieving users"

@pytest.mark.asyncio
async def test_update_user_success(db_session: AsyncSession, test_user: Users, current_user: Users):
    with patch("app.core.security.get_password_hash", return_value="hashed_updated_password"):
        update_data = UserUpdate(
            email="updated@example.com",
            password="UpdatedPassword123",
            first_name="Updated",
            phone_number="1112223333",
            job_title="Senior Developer",
            is_active=False
        )
        result = await update_user(db_session, test_user.user_id, update_data, current_user)
        assert result is not None
        assert result.user_id == test_user.user_id
        assert result.email == "updated@example.com"
        assert result.first_name == "Updated"
        assert result.phone_number == "1112223333"
        assert result.job_title == "Senior Developer"
        assert result.is_active is False
        assert result.updated_at is not None
        # Verify system log
        query = select(SystemLogs).where(SystemLogs.record_id == test_user.user_id, SystemLogs.action == SystemAction.USER_UPDATED)
        log_result = await db_session.execute(query)
        log = log_result.scalar_one_or_none()
        assert log is not None
        assert log.action == SystemAction.USER_UPDATED
        assert log.table_affected == "users"

@pytest.mark.asyncio
async def test_update_user_duplicate_email(db_session: AsyncSession, test_user: Users, current_user: Users):
    other_user = Users(
        email="other@example.com",
        password_hash="hashed_password",
        first_name="Other",
        last_name="User",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(other_user)
    await db_session.commit()

    update_data = UserUpdate(
        email="other@example.com"
    )
    with pytest.raises(HTTPException) as exc:
        await update_user(db_session, test_user.user_id, update_data, current_user)
    assert exc.value.status_code == 400
    assert exc.value.detail == "Email already registered"

@pytest.mark.asyncio
async def test_update_user_not_found(db_session: AsyncSession, current_user: Users):
    update_data = UserUpdate(
        first_name="Updated"
    )
    with pytest.raises(HTTPException) as exc:
        await update_user(db_session, 999, update_data, current_user)
    assert exc.value.status_code == 404
    assert exc.value.detail == "User not found"

@pytest.mark.asyncio
async def test_update_user_internal_error(db_session: AsyncSession, test_user: Users, current_user: Users):
    update_data = UserUpdate(
        first_name="Updated"
    )
    with patch.object(db_session, "commit", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await update_user(db_session, test_user.user_id, update_data, current_user)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error updating user"

@pytest.mark.asyncio
async def test_delete_user_success(db_session: AsyncSession, test_user: Users, current_user: Users):
    await delete_user(db_session, test_user.user_id, current_user)
    query = select(Users).where(Users.user_id == test_user.user_id, Users.is_active == True)
    result = await db_session.execute(query)
    assert result.scalar_one_or_none() is None
    # Verify system log
    query = select(SystemLogs).where(SystemLogs.record_id == test_user.user_id, SystemLogs.action == SystemAction.USER_DELETED)
    log_result = await db_session.execute(query)
    log = log_result.scalar_one_or_none()
    assert log is not None
    assert log.action == SystemAction.USER_DELETED
    assert log.table_affected == "users"

@pytest.mark.asyncio
async def test_delete_user_not_found(db_session: AsyncSession, current_user: Users):
    with pytest.raises(HTTPException) as exc:
        await delete_user(db_session, 999, current_user)
    assert exc.value.status_code == 404
    assert exc.value.detail == "User not found"

@pytest.mark.asyncio
async def test_delete_user_internal_error(db_session: AsyncSession, test_user: Users, current_user: Users):
    with patch.object(db_session, "commit", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await delete_user(db_session, test_user.user_id, current_user)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error deleting user"