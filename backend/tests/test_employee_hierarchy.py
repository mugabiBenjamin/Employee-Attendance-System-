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
from app.models.employee_hierarchy import EmployeeHierarchy
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
    return user

@pytest_asyncio.fixture
async def hr_user(db_session: AsyncSession):
    user = Users(
        email="hr@example.com",
        password_hash="hashed_password",
        first_name="HR",
        last_name="User",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    role = Roles(
        role_name="HR",
        description="HR role",
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
async def hr_auth_headers(hr_user: Users):
    access_token = create_access_token({"sub": str(hr_user.user_id)})
    return {"Authorization": f"Bearer {access_token}"}

@pytest_asyncio.fixture
async def test_hierarchy(db_session: AsyncSession, test_user: Users, manager_user: Users):
    hierarchy = EmployeeHierarchy(
        employee_id=test_user.user_id,
        manager_id=manager_user.user_id,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(hierarchy)
    await db_session.commit()
    await db_session.refresh(hierarchy)
    return hierarchy

@pytest.mark.asyncio
async def test_create_hierarchy_success(test_client: AsyncClient, hr_auth_headers: dict, test_user: Users, manager_user: Users):
    hierarchy_data = {
        "employee_id": test_user.user_id,
        "manager_id": manager_user.user_id
    }
    response = await test_client.post(
        "/api/v1/employee-hierarchy/",
        json=hierarchy_data,
        headers=hr_auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["employee_id"] == test_user.user_id
    assert data["manager_id"] == manager_user.user_id
    assert data["is_active"] is True
    assert data["hierarchy_id"] is not None

@pytest.mark.asyncio
async def test_create_hierarchy_invalid_employee(test_client: AsyncClient, hr_auth_headers: dict, manager_user: Users):
    hierarchy_data = {
        "employee_id": 999,
        "manager_id": manager_user.user_id
    }
    response = await test_client.post(
        "/api/v1/employee-hierarchy/",
        json=hierarchy_data,
        headers=hr_auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Employee not found"

@pytest.mark.asyncio
async def test_create_hierarchy_invalid_manager(test_client: AsyncClient, hr_auth_headers: dict, test_user: Users):
    hierarchy_data = {
        "employee_id": test_user.user_id,
        "manager_id": 999
    }
    response = await test_client.post(
        "/api/v1/employee-hierarchy/",
        json=hierarchy_data,
        headers=hr_auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Manager not found"

@pytest.mark.asyncio
async def test_create_hierarchy_self_reporting(test_client: AsyncClient, hr_auth_headers: dict, test_user: Users):
    hierarchy_data = {
        "employee_id": test_user.user_id,
        "manager_id": test_user.user_id
    }
    response = await test_client.post(
        "/api/v1/employee-hierarchy/",
        json=hierarchy_data,
        headers=hr_auth_headers
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Employee cannot be their own manager"

@pytest.mark.asyncio
async def test_create_hierarchy_already_exists(test_client: AsyncClient, hr_auth_headers: dict, test_hierarchy: EmployeeHierarchy):
    hierarchy_data = {
        "employee_id": test_hierarchy.employee_id,
        "manager_id": test_hierarchy.manager_id
    }
    response = await test_client.post(
        "/api/v1/employee-hierarchy/",
        json=hierarchy_data,
        headers=hr_auth_headers
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Employee already has a manager"

@pytest.mark.asyncio
async def test_create_hierarchy_unauthorized(test_client: AsyncClient, auth_headers: dict, test_user: Users, manager_user: Users):
    hierarchy_data = {
        "employee_id": test_user.user_id,
        "manager_id": manager_user.user_id
    }
    response = await test_client.post(
        "/api/v1/employee-hierarchy/",
        json=hierarchy_data,
        headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to create employee hierarchy"

@pytest.mark.asyncio
async def test_read_hierarchy_success(test_client: AsyncClient, hr_auth_headers: dict, test_hierarchy: EmployeeHierarchy):
    response = await test_client.get(
        f"/api/v1/employee-hierarchy/{test_hierarchy.hierarchy_id}",
        headers=hr_auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["hierarchy_id"] == test_hierarchy.hierarchy_id
    assert data["employee_id"] == test_hierarchy.employee_id
    assert data["manager_id"] == test_hierarchy.manager_id
    assert data["is_active"] is True

@pytest.mark.asyncio
async def test_read_hierarchy_not_found(test_client: AsyncClient, hr_auth_headers: dict):
    response = await test_client.get(
        "/api/v1/employee-hierarchy/999",
        headers=hr_auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Employee hierarchy not found"

@pytest.mark.asyncio
async def test_read_hierarchy_unauthorized(test_client: AsyncClient, auth_headers: dict, test_hierarchy: EmployeeHierarchy):
    response = await test_client.get(
        f"/api/v1/employee-hierarchy/{test_hierarchy.hierarchy_id}",
        headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to view employee hierarchy"

@pytest.mark.asyncio
async def test_list_hierarchies_success(test_client: AsyncClient, hr_auth_headers: dict, test_hierarchy: EmployeeHierarchy):
    response = await test_client.get(
        "/api/v1/employee-hierarchy/",
        headers=hr_auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(h["hierarchy_id"] == test_hierarchy.hierarchy_id for h in data)
    assert any(h["employee_id"] == test_hierarchy.employee_id for h in data)

@pytest.mark.asyncio
async def test_list_hierarchies_by_employee_id(test_client: AsyncClient, hr_auth_headers: dict, test_hierarchy: EmployeeHierarchy):
    response = await test_client.get(
        f"/api/v1/employee-hierarchy/?employee_id={test_hierarchy.employee_id}",
        headers=hr_auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert all(h["employee_id"] == test_hierarchy.employee_id for h in data)

@pytest.mark.asyncio
async def test_list_hierarchies_unauthorized(test_client: AsyncClient, auth_headers: dict):
    response = await test_client.get(
        "/api/v1/employee-hierarchy/",
        headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to view employee hierarchies"

@pytest.mark.asyncio
async def test_update_hierarchy_success(test_client: AsyncClient, hr_auth_headers: dict, test_hierarchy: EmployeeHierarchy, db_session: AsyncSession):
    new_manager = Users(
        email="newmanager@example.com",
        password_hash="hashed_password",
        first_name="New",
        last_name="Manager",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(new_manager)
    await db_session.commit()
    await db_session.refresh(new_manager)

    update_data = {
        "manager_id": new_manager.user_id
    }
    response = await test_client.put(
        f"/api/v1/employee-hierarchy/{test_hierarchy.hierarchy_id}",
        json=update_data,
        headers=hr_auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["hierarchy_id"] == test_hierarchy.hierarchy_id
    assert data["employee_id"] == test_hierarchy.employee_id
    assert data["manager_id"] == new_manager.user_id

@pytest.mark.asyncio
async def test_update_hierarchy_invalid_employee(test_client: AsyncClient, hr_auth_headers: dict, test_hierarchy: EmployeeHierarchy):
    update_data = {
        "employee_id": 999
    }
    response = await test_client.put(
        f"/api/v1/employee-hierarchy/{test_hierarchy.hierarchy_id}",
        json=update_data,
        headers=hr_auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Employee not found"

@pytest.mark.asyncio
async def test_update_hierarchy_invalid_manager(test_client: AsyncClient, hr_auth_headers: dict, test_hierarchy: EmployeeHierarchy):
    update_data = {
        "manager_id": 999
    }
    response = await test_client.put(
        f"/api/v1/employee-hierarchy/{test_hierarchy.hierarchy_id}",
        json=update_data,
        headers=hr_auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Manager not found"

@pytest.mark.asyncio
async def test_update_hierarchy_self_reporting(test_client: AsyncClient, hr_auth_headers: dict, test_hierarchy: EmployeeHierarchy):
    update_data = {
        "manager_id": test_hierarchy.employee_id
    }
    response = await test_client.put(
        f"/api/v1/employee-hierarchy/{test_hierarchy.hierarchy_id}",
        json=update_data,
        headers=hr_auth_headers
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Employee cannot be their own manager"

@pytest.mark.asyncio
async def test_update_hierarchy_already_exists(test_client: AsyncClient, hr_auth_headers: dict, test_hierarchy: EmployeeHierarchy, db_session: AsyncSession):
    new_employee = Users(
        email="newemployee@example.com",
        password_hash="hashed_password",
        first_name="New",
        last_name="Employee",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(new_employee)
    await db_session.commit()
    await db_session.refresh(new_employee)

    other_hierarchy = EmployeeHierarchy(
        employee_id=new_employee.user_id,
        manager_id=test_hierarchy.manager_id,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(other_hierarchy)
    await db_session.commit()

    update_data = {
        "employee_id": new_employee.user_id
    }
    response = await test_client.put(
        f"/api/v1/employee-hierarchy/{test_hierarchy.hierarchy_id}",
        json=update_data,
        headers=hr_auth_headers
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Employee already has a manager"

@pytest.mark.asyncio
async def test_update_hierarchy_not_found(test_client: AsyncClient, hr_auth_headers: dict):
    update_data = {
        "manager_id": 1
    }
    response = await test_client.put(
        "/api/v1/employee-hierarchy/999",
        json=update_data,
        headers=hr_auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Employee hierarchy not found"

@pytest.mark.asyncio
async def test_update_hierarchy_unauthorized(test_client: AsyncClient, auth_headers: dict, test_hierarchy: EmployeeHierarchy):
    update_data = {
        "manager_id": test_hierarchy.manager_id
    }
    response = await test_client.put(
        f"/api/v1/employee-hierarchy/{test_hierarchy.hierarchy_id}",
        json=update_data,
        headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to update employee hierarchies"

@pytest.mark.asyncio
async def test_delete_hierarchy_success(test_client: AsyncClient, hr_auth_headers: dict, test_hierarchy: EmployeeHierarchy):
    response = await test_client.delete(
        f"/api/v1/employee-hierarchy/{test_hierarchy.hierarchy_id}",
        headers=hr_auth_headers
    )
    assert response.status_code == 204
    response = await test_client.get(
        f"/api/v1/employee-hierarchy/{test_hierarchy.hierarchy_id}",
        headers=hr_auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Employee hierarchy not found"

@pytest.mark.asyncio
async def test_delete_hierarchy_not_found(test_client: AsyncClient, hr_auth_headers: dict):
    response = await test_client.delete(
        "/api/v1/employee-hierarchy/999",
        headers=hr_auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Employee hierarchy not found"

@pytest.mark.asyncio
async def test_delete_hierarchy_unauthorized(test_client: AsyncClient, auth_headers: dict, test_hierarchy: EmployeeHierarchy):
    response = await test_client.delete(
        f"/api/v1/employee-hierarchy/{test_hierarchy.hierarchy_id}",
        headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to delete employee hierarchies"

@pytest.mark.asyncio
async def test_create_hierarchy_internal_server_error(test_client: AsyncClient, hr_auth_headers: dict, test_user: Users, manager_user: Users):
    with patch("app.core.database.AsyncSessionLocal", side_effect=Exception("Database error")):
        hierarchy_data = {
            "employee_id": test_user.user_id,
            "manager_id": manager_user.user_id
        }
        response = await test_client.post(
            "/api/v1/employee-hierarchy/",
            json=hierarchy_data,
            headers=hr_auth_headers
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Error creating employee hierarchy"