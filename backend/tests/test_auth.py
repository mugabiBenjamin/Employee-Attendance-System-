import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from app.core.database import AsyncSessionLocal
from app.models.users import Users
from app.main import app
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, verify_password

@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()

@pytest_asyncio.fixture
async def test_client():
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    user = Users(
        email="test@example.com",
        password_hash=verify_password("testpassword", "salt")["password_hash"],
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
async def inactive_user(db_session: AsyncSession):
    user = Users(
        email="inactive@example.com",
        password_hash=verify_password("testpassword", "salt")["password_hash"],
        first_name="Inactive",
        last_name="User",
        is_active=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest.mark.asyncio
async def test_login_success(test_client: AsyncClient, test_user: Users):
    form_data = {
        "username": "test@example.com",
        "password": "testpassword"
    }
    response = await test_client.post(
        "/api/v1/auth/token",
        data=form_data
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["access_token"] is not None
    assert data["refresh_token"] is not None

@pytest.mark.asyncio
async def test_login_invalid_credentials(test_client: AsyncClient):
    form_data = {
        "username": "wrong@example.com",
        "password": "wrongpassword"
    }
    response = await test_client.post(
        "/api/v1/auth/token",
        data=form_data
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    assert response.headers["WWW-Authenticate"] == "Bearer"

@pytest.mark.asyncio
async def test_login_inactive_user(test_client: AsyncClient, inactive_user: Users):
    form_data = {
        "username": "inactive@example.com",
        "password": "testpassword"
    }
    response = await test_client.post(
        "/api/v1/auth/token",
        data=form_data
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    assert response.headers["WWW-Authenticate"] == "Bearer"

@pytest.mark.asyncio
async def test_refresh_token_success(test_client: AsyncClient, test_user: Users):
    refresh_token = create_refresh_token({"sub": str(test_user.user_id)})
    response = await test_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["access_token"] is not None
    assert data["refresh_token"] is not None

@pytest.mark.asyncio
async def test_refresh_token_invalid(test_client: AsyncClient):
    response = await test_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid_token"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid refresh token"
    assert response.headers["WWW-Authenticate"] == "Bearer"

@pytest.mark.asyncio
async def test_refresh_token_inactive_user(test_client: AsyncClient, inactive_user: Users):
    refresh_token = create_refresh_token({"sub": str(inactive_user.user_id)})
    response = await test_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "User not found or inactive"
    assert response.headers["WWW-Authenticate"] == "Bearer"

@pytest.mark.asyncio
async def test_login_internal_server_error(test_client: AsyncClient, test_user: Users):
    with patch("app.core.database.AsyncSessionLocal", side_effect=Exception("Database error")):
        form_data = {
            "username": "test@example.com",
            "password": "testpassword"
        }
        response = await test_client.post(
            "/api/v1/auth/token",
            data=form_data
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Internal server error during authentication"

@pytest.mark.asyncio
async def test_refresh_token_internal_server_error(test_client: AsyncClient, test_user: Users):
    with patch("app.core.database.AsyncSessionLocal", side_effect=Exception("Database error")):
        refresh_token = create_refresh_token({"sub": str(test_user.user_id)})
        response = await test_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token}
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Internal server error during token refresh"