import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from app.main import app, AsyncSessionLocal
from app.models.system_logs import SystemLogs
from app.core.enums import SystemAction
from app.core.config import settings
from app.models.users import Users

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
def client():
    return TestClient(app)

@pytest.mark.asyncio
async def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": f"Welcome to {settings.APP_NAME} API"}

@pytest.mark.asyncio
async def test_middleware_log_login(db_session: AsyncSession, client, test_user: Users):
    with patch("app.main.AsyncSessionLocal", return_value=AsyncMock()) as mock_session, \
         patch.object(mock_session.return_value.__aenter__.return_value, "commit", return_value=None):
        # Mock the request state to include a user
        with patch("app.main.Request.state", new_callable=AsyncMock) as mock_request_state:
            mock_request_state.user = test_user
            response = client.post("/api/v1/auth/token")
            assert response.status_code == 200  # Assuming the endpoint exists and returns 200
            # Verify system log
            query = select(SystemLogs).where(SystemLogs.action == SystemAction.LOGIN.value)
            result = await db_session.execute(query)
            log = result.scalar_one_or_none()
            assert log is not None
            assert log.user_id == test_user.user_id
            assert log.action == SystemAction.LOGIN.value
            assert log.entity_type == "auth"
            assert log.created_at is not None

@pytest.mark.asyncio
async def test_middleware_log_logout(db_session: AsyncSession, client, test_user: Users):
    with patch("app.main.AsyncSessionLocal", return_value=AsyncMock()) as mock_session, \
         patch.object(mock_session.return_value.__aenter__.return_value, "commit", return_value=None):
        with patch("app.main.Request.state", new_callable=AsyncMock) as mock_request_state:
            mock_request_state.user = test_user
            response = client.post("/api/v1/auth/logout")
            assert response.status_code == 200  # Assuming the endpoint exists and returns 200
            # Verify system log
            query = select(SystemLogs).where(SystemLogs.action == SystemAction.LOGOUT.value)
            result = await db_session.execute(query)
            log = result.scalar_one_or_none()
            assert log is not None
            assert log.user_id == test_user.user_id
            assert log.action == SystemAction.LOGOUT.value
            assert log.entity_type == "auth"
            assert log.created_at is not None

@pytest.mark.asyncio
async def test_middleware_log_clock_in(db_session: AsyncSession, client, test_user: Users):
    with patch("app.main.AsyncSessionLocal", return_value=AsyncMock()) as mock_session, \
         patch.object(mock_session.return_value.__aenter__.return_value, "commit", return_value=None):
        with patch("app.main.Request.state", new_callable=AsyncMock) as mock_request_state:
            mock_request_state.user = test_user
            response = client.post("/api/v1/attendance-records/clock")
            assert response.status_code == 200  # Assuming the endpoint exists and returns 200
            # Verify system log
            query = select(SystemLogs).where(SystemLogs.action == SystemAction.CLOCK_IN.value)
            result = await db_session.execute(query)
            log = result.scalar_one_or_none()
            assert log is not None
            assert log.user_id == test_user.user_id
            assert log.action == SystemAction.CLOCK_IN.value
            assert log.entity_type == "attendance-records"
            assert log.created_at is not None

@pytest.mark.asyncio
async def test_middleware_log_approve_leave(db_session: AsyncSession, client, test_user: Users):
    with patch("app.main.AsyncSessionLocal", return_value=AsyncMock()) as mock_session, \
         patch.object(mock_session.return_value.__aenter__.return_value, "commit", return_value=None):
        with patch("app.main.Request.state", new_callable=AsyncMock) as mock_request_state:
            mock_request_state.user = test_user
            response = client.post("/api/v1/leave-requests/approve")
            assert response.status_code == 200  # Assuming the endpoint exists and returns 200
            # Verify system log
            query = select(SystemLogs).where(SystemLogs.action == SystemAction.APPROVE_LEAVE.value)
            result = await db_session.execute(query)
            log = result.scalar_one_or_none()
            assert log is not None
            assert log.user_id == test_user.user_id
            assert log.action == SystemAction.APPROVE_LEAVE.value
            assert log.entity_type == "leave-requests"
            assert log.created_at is not None

@pytest.mark.asyncio
async def test_middleware_log_reject_leave(db_session: AsyncSession, client, test_user: Users):
    with patch("app.main.AsyncSessionLocal", return_value=AsyncMock()) as mock_session, \
         patch.object(mock_session.return_value.__aenter__.return_value, "commit", return_value=None):
        with patch("app.main.Request.state", new_callable=AsyncMock) as mock_request_state:
            mock_request_state.user = test_user
            response = client.post("/api/v1/leave-requests/reject")
            assert response.status_code == 200  # Assuming the endpoint exists and returns 200
            # Verify system log
            query = select(SystemLogs).where(SystemLogs.action == SystemAction.REJECT_LEAVE.value)
            result = await db_session.execute(query)
            log = result.scalar_one_or_none()
            assert log is not None
            assert log.user_id == test_user.user_id
            assert log.action == SystemAction.REJECT_LEAVE.value
            assert log.entity_type == "leave-requests"
            assert log.created_at is not None

@pytest.mark.asyncio
async def test_middleware_log_generic_post(db_session: AsyncSession, client, test_user: Users):
    with patch("app.main.AsyncSessionLocal", return_value=AsyncMock()) as mock_session, \
         patch.object(mock_session.return_value.__aenter__.return_value, "commit", return_value=None):
        with patch("app.main.Request.state", new_callable=AsyncMock) as mock_request_state:
            mock_request_state.user = test_user
            response = client.post("/api/v1/some-endpoint")
            assert response.status_code == 404  # Assuming the endpoint does not exist
            # Verify system log for generic POST
            query = select(SystemLogs).where(SystemLogs.action == SystemAction.POST.value)
            result = await db_session.execute(query)
            log = result.scalar_one_or_none()
            assert log is not None
            assert log.user_id == test_user.user_id
            assert log.action == SystemAction.POST.value
            assert log.entity_type == "some-endpoint"
            assert log.created_at is not None

@pytest.mark.asyncio
async def test_middleware_log_no_user(db_session: AsyncSession, client):
    with patch("app.main.AsyncSessionLocal", return_value=AsyncMock()) as mock_session, \
         patch.object(mock_session.return_value.__aenter__.return_value, "commit", return_value=None):
        response = client.post("/api/v1/auth/token")
        assert response.status_code == 200  # Assuming the endpoint exists and returns 200
        # Verify system log with no user
        query = select(SystemLogs).where(SystemLogs.action == SystemAction.LOGIN.value)
        result = await db_session.execute(query)
        log = result.scalar_one_or_none()
        assert log is not None
        assert log.user_id is None
        assert log.action == SystemAction.LOGIN.value
        assert log.entity_type == "auth"
        assert log.created_at is not None

@pytest.mark.asyncio
async def test_middleware_log_database_error(db_session: AsyncSession, client, test_user: Users):
    with patch("app.main.AsyncSessionLocal", return_value=AsyncMock()) as mock_session, \
         patch.object(mock_session.return_value.__aenter__.return_value, "commit", side_effect=Exception("Database error")):
        with patch("app.main.Request.state", new_callable=AsyncMock) as mock_request_state:
            mock_request_state.user = test_user
            response = client.post("/api/v1/auth/token")
            assert response.status_code == 200  # Assuming the endpoint exists and returns 200
            # No assertion on log since database error prevents logging, but request should still complete

@pytest.mark.asyncio
async def test_middleware_no_log_for_untracked_action(db_session: AsyncSession, client, test_user: Users):
    with patch("app.main.AsyncSessionLocal", return_value=AsyncMock()) as mock_session, \
         patch.object(mock_session.return_value.__aenter__.return_value, "commit", return_value=None):
        with patch("app.main.Request.state", new_callable=AsyncMock) as mock_request_state:
            mock_request_state.user = test_user
            response = client.get("/api/v1/some-endpoint")
            assert response.status_code == 404  # Assuming the endpoint does not exist
            # Verify no system log is created for untracked action (GET)
            query = select(SystemLogs)
            result = await db_session.execute(query)
            log = result.scalar_one_or_none()
            assert log is None