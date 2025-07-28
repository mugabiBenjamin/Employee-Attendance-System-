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
from app.models.employee_emergency_contacts import EmployeeEmergencyContacts
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
async def test_emergency_contact(db_session: AsyncSession, test_user: Users):
    contact = EmployeeEmergencyContacts(
        user_id=test_user.user_id,
        contact_name="Jane Doe",
        relationship="Spouse",
        phone_number="1234567890",
        email="jane@example.com",
        address="123 Main St",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)
    return contact

@pytest.mark.asyncio
async def test_create_emergency_contact_success(test_client: AsyncClient, hr_auth_headers: dict, test_user: Users):
    contact_data = {
        "user_id": test_user.user_id,
        "contact_name": "John Doe",
        "relationship": "Friend",
        "phone_number": "0987654321",
        "email": "john@example.com",
        "address": "456 Elm St"
    }
    response = await test_client.post(
        "/api/v1/emergency-contacts/",
        json=contact_data,
        headers=hr_auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == test_user.user_id
    assert data["contact_name"] == "John Doe"
    assert data["relationship"] == "Friend"
    assert data["phone_number"] == "0987654321"
    assert data["email"] == "john@example.com"
    assert data["address"] == "456 Elm St"
    assert data["is_active"] is True

@pytest.mark.asyncio
async def test_create_emergency_contact_invalid_user(test_client: AsyncClient, hr_auth_headers: dict):
    contact_data = {
        "user_id": 999,
        "contact_name": "John Doe",
        "relationship": "Friend",
        "phone_number": "0987654321",
        "email": "john@example.com",
        "address": "456 Elm St"
    }
    response = await test_client.post(
        "/api/v1/emergency-contacts/",
        json=contact_data,
        headers=hr_auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"

@pytest.mark.asyncio
async def test_create_emergency_contact_unauthorized(test_client: AsyncClient, auth_headers: dict, test_user: Users):
    contact_data = {
        "user_id": test_user.user_id,
        "contact_name": "John Doe",
        "relationship": "Friend",
        "phone_number": "0987654321"
    }
    response = await test_client.post(
        "/api/v1/emergency-contacts/",
        json=contact_data,
        headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to create emergency contacts"

@pytest.mark.asyncio
async def test_read_emergency_contact_success(test_client: AsyncClient, hr_auth_headers: dict, test_emergency_contact: EmployeeEmergencyContacts):
    response = await test_client.get(
        f"/api/v1/emergency-contacts/{test_emergency_contact.contact_id}",
        headers=hr_auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["contact_id"] == test_emergency_contact.contact_id
    assert data["user_id"] == test_emergency_contact.user_id
    assert data["contact_name"] == test_emergency_contact.contact_name
    assert data["relationship"] == test_emergency_contact.relationship
    assert data["phone_number"] == test_emergency_contact.phone_number

@pytest.mark.asyncio
async def test_read_emergency_contact_not_found(test_client: AsyncClient, hr_auth_headers: dict):
    response = await test_client.get(
        "/api/v1/emergency-contacts/999",
        headers=hr_auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Emergency contact not found"

@pytest.mark.asyncio
async def test_read_emergency_contact_unauthorized(test_client: AsyncClient, auth_headers: dict, test_emergency_contact: EmployeeEmergencyContacts):
    response = await test_client.get(
        f"/api/v1/emergency-contacts/{test_emergency_contact.contact_id}",
        headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to view emergency contacts"

@pytest.mark.asyncio
async def test_list_emergency_contacts_success(test_client: AsyncClient, hr_auth_headers: dict, test_emergency_contact: EmployeeEmergencyContacts):
    response = await test_client.get(
        "/api/v1/emergency-contacts/",
        headers=hr_auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(contact["contact_id"] == test_emergency_contact.contact_id for contact in data)
    assert any(contact["user_id"] == test_emergency_contact.user_id for contact in data)

@pytest.mark.asyncio
async def test_list_emergency_contacts_by_user_id(test_client: AsyncClient, hr_auth_headers: dict, test_emergency_contact: EmployeeEmergencyContacts):
    response = await test_client.get(
        f"/api/v1/emergency-contacts/?user_id={test_emergency_contact.user_id}",
        headers=hr_auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert all(contact["user_id"] == test_emergency_contact.user_id for contact in data)

@pytest.mark.asyncio
async def test_list_emergency_contacts_unauthorized(test_client: AsyncClient, auth_headers: dict):
    response = await test_client.get(
        "/api/v1/emergency-contacts/",
        headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to view emergency contacts"

@pytest.mark.asyncio
async def test_list_emergency_contacts_unauthorized_other_user(test_client: AsyncClient, auth_headers: dict, test_user: Users):
    response = await test_client.get(
        f"/api/v1/emergency-contacts/?user_id={test_user.user_id + 1}",
        headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to view other users' emergency contacts"

@pytest.mark.asyncio
async def test_update_emergency_contact_success(test_client: AsyncClient, hr_auth_headers: dict, test_emergency_contact: EmployeeEmergencyContacts):
    update_data = {
        "contact_name": "Updated Name",
        "relationship": "Parent",
        "phone_number": "1112223333",
        "email": "updated@example.com",
        "address": "789 Oak St"
    }
    response = await test_client.put(
        f"/api/v1/emergency-contacts/{test_emergency_contact.contact_id}",
        json=update_data,
        headers=hr_auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["contact_id"] == test_emergency_contact.contact_id
    assert data["contact_name"] == "Updated Name"
    assert data["relationship"] == "Parent"
    assert data["phone_number"] == "1112223333"
    assert data["email"] == "updated@example.com"
    assert data["address"] == "789 Oak St"

@pytest.mark.asyncio
async def test_update_emergency_contact_not_found(test_client: AsyncClient, hr_auth_headers: dict):
    update_data = {
        "contact_name": "Updated Name",
        "relationship": "Parent"
    }
    response = await test_client.put(
        "/api/v1/emergency-contacts/999",
        json=update_data,
        headers=hr_auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Emergency contact not found"

@pytest.mark.asyncio
async def test_update_emergency_contact_unauthorized(test_client: AsyncClient, auth_headers: dict, test_emergency_contact: EmployeeEmergencyContacts):
    update_data = {
        "contact_name": "Updated Name",
        "relationship": "Parent"
    }
    response = await test_client.put(
        f"/api/v1/emergency-contacts/{test_emergency_contact.contact_id}",
        json=update_data,
        headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to update emergency contacts"

@pytest.mark.asyncio
async def test_update_emergency_contact_unauthorized_other_user(test_client: AsyncClient, auth_headers: dict, test_emergency_contact: EmployeeEmergencyContacts, db_session: AsyncSession):
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
    other_auth_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(other_user.user_id)})}"}
    update_data = {
        "contact_name": "Updated Name",
        "relationship": "Parent"
    }
    response = await test_client.put(
        f"/api/v1/emergency-contacts/{test_emergency_contact.contact_id}",
        json=update_data,
        headers=other_auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to update this contact"

@pytest.mark.asyncio
async def test_delete_emergency_contact_success(test_client: AsyncClient, hr_auth_headers: dict, test_emergency_contact: EmployeeEmergencyContacts):
    response = await test_client.delete(
        f"/api/v1/emergency-contacts/{test_emergency_contact.contact_id}",
        headers=hr_auth_headers
    )
    assert response.status_code == 204
    response = await test_client.get(
        f"/api/v1/emergency-contacts/{test_emergency_contact.contact_id}",
        headers=hr_auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Emergency contact not found"

@pytest.mark.asyncio
async def test_delete_emergency_contact_not_found(test_client: AsyncClient, hr_auth_headers: dict):
    response = await test_client.delete(
        "/api/v1/emergency-contacts/999",
        headers=hr_auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Emergency contact not found"

@pytest.mark.asyncio
async def test_delete_emergency_contact_unauthorized(test_client: AsyncClient, auth_headers: dict, test_emergency_contact: EmployeeEmergencyContacts):
    response = await test_client.delete(
        f"/api/v1/emergency-contacts/{test_emergency_contact.contact_id}",
        headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to delete emergency contacts"

@pytest.mark.asyncio
async def test_delete_emergency_contact_unauthorized_other_user(test_client: AsyncClient, test_emergency_contact: EmployeeEmergencyContacts, db_session: AsyncSession):
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
    other_auth_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(other_user.user_id)})}"}
    response = await test_client.delete(
        f"/api/v1/emergency-contacts/{test_emergency_contact.contact_id}",
        headers=other_auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to delete this contact"

@pytest.mark.asyncio
async def test_create_emergency_contact_internal_server_error(test_client: AsyncClient, hr_auth_headers: dict, test_user: Users):
    with patch("app.core.database.AsyncSessionLocal", side_effect=Exception("Database error")):
        contact_data = {
            "user_id": test_user.user_id,
            "contact_name": "John Doe",
            "relationship": "Friend",
            "phone_number": "0987654321"
        }
        response = await test_client.post(
            "/api/v1/emergency-contacts/",
            json=contact_data,
            headers=hr_auth_headers
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Error creating emergency contact"