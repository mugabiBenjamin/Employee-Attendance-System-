from fastapi import HTTPException
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from app.core.database import AsyncSessionLocal
from app.models.users import Users
from app.models.system_logs import SystemLogs
from app.services.system_log_service import create_system_log, get_system_log_by_id, get_system_logs, get_system_logs_by_user
from app.core.config import settings
from app.core.enums import SystemAction
from pydantic import BaseModel, ConfigDict

# Mock schemas for testing
class SystemLogCreate(BaseModel):
    user_id: int | None = None
    action: SystemAction
    table_affected: str | None = None
    record_id: int | None = None
    old_values: dict | None = None
    new_values: dict | None = None
    ip_address: str | None = None

    model_config = ConfigDict(from_attributes=True)

class SystemLogOut(BaseModel):
    log_id: int
    user_id: int | None
    action: SystemAction
    table_affected: str | None
    record_id: int | None
    old_values: dict | None
    new_values: dict | None
    ip_ip_address: str | None
    timestamp: datetime

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
async def test_log(db_session: AsyncSession, test_user: Users):
    log = SystemLogs(
        user_id=test_user.user_id,
        action=SystemAction.LOGIN,
        table_affected="users",
        record_id=1,
        old_values={"status": "inactive"},
        new_values={"status": "active"},
        ip_address="127.0.0.1",
        timestamp=datetime.now(timezone.utc)
    )
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)
    return log

@pytest.mark.asyncio
async def test_create_system_log_success(db_session: AsyncSession, test_user: Users):
    log_data = SystemLogCreate(
        user_id=test_user.user_id,
        action=SystemAction.LOGIN,
        table_affected="users",
        record_id=1,
        old_values={"status": "inactive"},
        new_values={"status": "active"},
        ip_address="127.0.0.1"
    )
    result = await create_system_log(db_session, log_data)
    assert result is not None
    assert result.user_id == test_user.user_id
    assert result.action == SystemAction.LOGIN
    assert result.table_affected == "users"
    assert result.record_id == 1
    assert result.old_values == {"status": "inactive"}
    assert result.new_values == {"status": "active"}
    assert result.ip_address == "127.0.0.1"
    assert result.timestamp is not None

@pytest.mark.asyncio
async def test_create_system_log_no_user_id(db_session: AsyncSession):
    log_data = SystemLogCreate(
        user_id=None,
        action=SystemAction.LOGOUT,
        table_affected="users",
        record_id=None,
        old_values=None,
        new_values=None,
        ip_address="192.168.1.1"
    )
    result = await create_system_log(db_session, log_data)
    assert result is not None
    assert result.user_id is None
    assert result.action == SystemAction.LOGOUT
    assert result.table_affected == "users"
    assert result.record_id is None
    assert result.old_values is None
    assert result.new_values is None
    assert result.ip_address == "192.168.1.1"
    assert result.timestamp is not None

@pytest.mark.asyncio
async def test_create_system_log_invalid_user(db_session: AsyncSession):
    log_data = SystemLogCreate(
        user_id=999,
        action=SystemAction.LOGIN,
        table_affected="users",
        record_id=1,
        ip_address="127.0.0.1"
    )
    with pytest.raises(HTTPException) as exc:
        await create_system_log(db_session, log_data)
    assert exc.value.status_code == 404
    assert exc.value.detail == "User not found"

@pytest.mark.asyncio
async def test_create_system_log_internal_error(db_session: AsyncSession, test_user: Users):
    log_data = SystemLogCreate(
        user_id=test_user.user_id,
        action=SystemAction.LOGIN,
        table_affected="users",
        record_id=1,
        ip_address="127.0.0.1"
    )
    with patch.object(db_session, "commit", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await create_system_log(db_session, log_data)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error creating system log"

@pytest.mark.asyncio
async def test_get_system_log_by_id_success(db_session: AsyncSession, test_log: SystemLogs):
    result = await get_system_log_by_id(db_session, test_log.log_id)
    assert result is not None
    assert result.log_id == test_log.log_id
    assert result.user_id == test_log.user_id
    assert result.action == test_log.action
    assert result.table_affected == test_log.table_affected
    assert result.record_id == test_log.record_id
    assert result.old_values == test_log.old_values
    assert result.new_values == test_log.new_values
    assert result.ip_address == test_log.ip_address

@pytest.mark.asyncio
async def test_get_system_log_by_id_not_found(db_session: AsyncSession):
    result = await get_system_log_by_id(db_session, 999)
    assert result is None

@pytest.mark.asyncio
async def test_get_system_log_by_id_internal_error(db_session: AsyncSession):
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await get_system_log_by_id(db_session, 1)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error retrieving system log"

@pytest.mark.asyncio
async def test_get_system_logs_success(db_session: AsyncSession, test_log: SystemLogs):
    result = await get_system_logs(db_session, skip=0, limit=10)
    assert len(result) >= 1
    assert any(log.log_id == test_log.log_id for log in result)
    assert any(log.user_id == test_log.user_id for log in result)
    assert any(log.action == test_log.action for log in result)

@pytest.mark.asyncio
async def test_get_system_logs_empty(db_session: AsyncSession):
    result = await get_system_logs(db_session, skip=0, limit=10)
    assert len(result) == 0

@pytest.mark.asyncio
async def test_get_system_logs_internal_error(db_session: AsyncSession):
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await get_system_logs(db_session, skip=0, limit=10)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error retrieving system logs"

@pytest.mark.asyncio
async def test_get_system_logs_by_user_success(db_session: AsyncSession, test_log: SystemLogs, test_user: Users):
    result = await get_system_logs_by_user(db_session, test_user.user_id, skip=0, limit=10)
    assert len(result) >= 1
    assert all(log.user_id == test_user.user_id for log in result)
    assert any(log.log_id == test_log.log_id for log in result)

@pytest.mark.asyncio
async def test_get_system_logs_by_user_not_found(db_session: AsyncSession):
    with pytest.raises(HTTPException) as exc:
        await get_system_logs_by_user(db_session, 999, skip=0, limit=10)
    assert exc.value.status_code == 404
    assert exc.value.detail == "User not found"

@pytest.mark.asyncio
async def test_get_system_logs_by_user_empty(db_session: AsyncSession, test_user: Users):
    result = await get_system_logs_by_user(db_session, test_user.user_id, skip=0, limit=10)
    assert len(result) == 0

@pytest.mark.asyncio
async def test_get_system_logs_by_user_internal_error(db_session: AsyncSession, test_user: Users):
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await get_system_logs_by_user(db_session, test_user.user_id, skip=0, limit=10)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error retrieving system logs for user"