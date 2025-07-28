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
from app.models.departments import Departments
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.main import app
from app.core.config import settings
from app.core.security import create_access_token

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
async def manager_user(db_session: AsyncSession):
    user = Users(
        email="manager@example.com",
        password_hash="hashed_password",
        first_name="Manager",
        last_name="User",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    role = Roles(
        role_name="Manager",
        description="Manager role",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    user_role = UserRoles(
        user_id=user.user_id,
        role_id=role.role_id,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(user_role)
    await db_session.commit()
    return user

@pytest_asyncio.fixture
async def auth_headers(test_user: Users):
    access_token = create_access_token({"sub": str(test_user.user_id)})
    return {"Authorization": f"Bearer {access_token}"}

@pytest_asyncio.fixture
async def manager_auth_headers(manager_user: Users):
    access_token = create_access_token({"sub": str(manager_user.user_id)})
    return {"Authorization": f"Bearer {access_token}"}

@pytest_asyncio.fixture
async def test_department(db_session: AsyncSession):
    department = Departments(
        name="Test Department",
        description="Test Description",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(department)
    await db_session.commit()
    await db_session.refresh(department)
    return department

@pytest.mark.asyncio
async def test_create_department_success(test_client: AsyncClient, manager_auth_headers: dict):
    department_data = {
        "name": "New Department",
        "description": "A new department"
    }
    response = await test_client.post(
        "/api/v1/departments/",
        json=department_data,
        headers=manager_auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "New Department"
    assert data["description"] == "A new department"
    assert data["is_active"] is True
    assert data["department_id"] is not None

@pytest.mark.asyncio
async def test_create_department_duplicate_name(test_client: AsyncClient, manager_auth_headers: dict, test_department: Departments):
    department_data = {
        "name": "Test Department",
        "description": "Duplicate department"
    }
    response = await test_client.post(
        "/api/v1/departments/",
        json=department_data,
        headers=manager_auth_headers
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Department name already exists"

@pytest.mark.asyncio
async def test_create_department_unauthorized(test_client: AsyncClient, auth_headers: dict):
    department_data = {
        "name": "New Department",
        "description": "A new department"
    }
    response = await test_client.post(
        "/api/v1/departments/",
        json=department_data,
        headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to create departments"

@pytest.mark.asyncio
async def test_read_department_success(test_client: AsyncClient, manager_auth_headers: dict, test_department: Departments):
    response = await test_client.get(
        f"/api/v1/departments/{test_department.department_id}",
        headers=manager_auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["department_id"] == test_department.department_id
    assert data["name"] == test_department.name
    assert data["description"] == test_department.description
    assert data["is_active"] is True

@pytest.mark.asyncio
async def test_read_department_not_found(test_client: AsyncClient, manager_auth_headers: dict):
    response = await test_client.get(
        "/api/v1/departments/999",
        headers=manager_auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Department not found"

@pytest.mark.asyncio
async def test_read_department_unauthorized(test_client: AsyncClient, auth_headers: dict, test_department: Departments):
    response = await test_client.get(
        f"/api/v1/departments/{test_department.department_id}",
        headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to view departments"

@pytest.mark.asyncio
async def test_list_departments_success(test_client: AsyncClient, manager_auth_headers: dict, test_department: Departments):
    response = await test_client.get(
        "/api/v1/departments/",
        headers=manager_auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(dept["department_id"] == test_department.department_id for dept in data)
    assert any(dept["name"] == test_department.name for dept in data)

@pytest.mark.asyncio
async def test_list_departments_unauthorized(test_client: AsyncClient, auth_headers: dict):
    response = await test_client.get(
        "/api/v1/departments/",
        headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to view departments"

@pytest.mark.asyncio
async def test_update_department_success(test_client: AsyncClient, manager_auth_headers: dict, test_department: Departments):
    update_data = {
        "name": "Updated Department",
        "description": "Updated Description"
    }
    response = await test_client.put(
        f"/api/v1/departments/{test_department.department_id}",
        json=update_data,
        headers=manager_auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Department"
    assert data["description"] == "Updated Description"
    assert data["department_id"] == test_department.department_id

@pytest.mark.asyncio
async def test_update_department_duplicate_name(test_client: AsyncClient, manager_auth_headers: dict, test_department: Departments, db_session: AsyncSession):
    other_department = Departments(
        name="Other Department",
        description="Other Description",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(other_department)
    await db_session.commit()
    update_data = {
        "name": "Other Department",
        "description": "Trying to duplicate"
    }
    response = await test_client.put(
        f"/api/v1/departments/{test_department.department_id}",
        json=update_data,
        headers=manager_auth_headers
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Department name already exists"

@pytest.mark.asyncio
async def test_update_department_not_found(test_client: AsyncClient, manager_auth_headers: dict):
    update_data = {
        "name": "Updated Department",
        "description": "Updated Description"
    }
    response = await test_client.put(
        "/api/v1/departments/999",
        json=update_data,
        headers=manager_auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Department not found"

@pytest.mark.asyncio
async def test_update_department_unauthorized(test_client: AsyncClient, auth_headers: dict, test_department: Departments):
    update_data = {
        "name": "Updated Department",
        "description": "Updated Description"
    }
    response = await test_client.put(
        f"/api/v1/departments/{test_department.department_id}",
        json=update_data,
        headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to update departments"

@pytest.mark.asyncio
async def test_delete_department_success(test_client: AsyncClient, manager_auth_headers: dict, test_department: Departments):
    response = await test_client.delete(
        f"/api/v1/departments/{test_department.department_id}",
        headers=manager_auth_headers
    )
    assert response.status_code == 204
    response = await test_client.get(
        f"/api/v1/departments/{test_department.department_id}",
        headers=manager_auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Department not found"

@pytest.mark.asyncio
async def test_delete_department_not_found(test_client: AsyncClient, manager_auth_headers: dict):
    response = await test_client.delete(
        "/api/v1/departments/999",
        headers=manager_auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Department not found"

@pytest.mark.asyncio
async def test_delete_department_unauthorized(test_client: AsyncClient, auth_headers: dict, test_department: Departments):
    response = await test_client.delete(
        f"/api/v1/departments/{test_department.department_id}",
        headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to delete departments"

@pytest.mark.asyncio
async def test_create_department_internal_server_error(test_client: AsyncClient, manager_auth_headers: dict):
    with patch("app.core.database.AsyncSessionLocal", side_effect=Exception("Database error")):
        department_data = {
            "name": "New Department",
            "description": "A new department"
        }
        response = await test_client.post(
            "/api/v1/departments/",
            json=department_data,
            headers=manager_auth_headers
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Error creating department"