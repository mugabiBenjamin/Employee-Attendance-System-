import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone, date
from unittest.mock import AsyncMock, patch
from app.core.database import AsyncSessionLocal
from app.models.users import Users
from app.models.attendance_records import AttendanceRecords
from app.models.time_corrections import TimeCorrections
from app.models.overtime_records import OvertimeRecords
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
async def attendance_record(db_session: AsyncSession, test_user: Users):
    record = AttendanceRecords(
        user_id=test_user.user_id,
        clock_in_time=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_active=True
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    return record

@pytest.mark.asyncio
async def test_clock_in_success(test_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_user: Users):
    response = await test_client.post(
        "/api/v1/attendance-records/clock",
        json={"action": "clock_in"},
        headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == test_user.user_id
    assert data["clock_in_time"] is not None
    assert data["clock_out_time"] is None
    assert data["is_active"] is True

@pytest.mark.asyncio
async def test_clock_in_already_active(test_client: AsyncClient, auth_headers: dict, attendance_record: AttendanceRecords):
    response = await test_client.post(
        "/api/v1/attendance-records/clock",
        json={"action": "clock_in"},
        headers=auth_headers
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Active clock-in already exists"

@pytest.mark.asyncio
async def test_clock_out_success(test_client: AsyncClient, auth_headers: dict, attendance_record: AttendanceRecords):
    response = await test_client.post(
        "/api/v1/attendance-records/clock",
        json={"action": "clock_out"},
        headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["record_id"] == attendance_record.record_id
    assert data["clock_out_time"] is not None

@pytest.mark.asyncio
async def test_clock_out_no_active_clock_in(test_client: AsyncClient, auth_headers: dict, db_session: AsyncSession):
    response = await test_client.post(
        "/api/v1/attendance-records/clock",
        json={"action": "clock_out"},
        headers=auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "No active clock-in found"

@pytest.mark.asyncio
async def test_get_attendance_history(test_client: AsyncClient, auth_headers: dict, attendance_record: AttendanceRecords):
    response = await test_client.get(
        "/api/v1/attendance-records/history",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["record_id"] == attendance_record.record_id

@pytest.mark.asyncio
async def test_request_time_correction_success(test_client: AsyncClient, auth_headers: dict, attendance_record: AttendanceRecords):
    correction_data = {
        "record_id": attendance_record.record_id,
        "corrected_clock_in": "2025-07-28T08:00:00Z",
        "corrected_clock_out": "2025-07-28T17:00:00Z",
        "reason": "Incorrect clock-in time"
    }
    response = await test_client.post(
        "/api/v1/attendance-records/time-correction",
        json=correction_data,
        headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["record_id"] == attendance_record.record_id
    assert data["reason"] == "Incorrect clock-in time"
    assert data["status"] == "pending"

@pytest.mark.asyncio
async def test_request_time_correction_invalid_record(test_client: AsyncClient, auth_headers: dict):
    correction_data = {
        "record_id": 999,
        "corrected_clock_in": "2025-07-28T08:00:00Z",
        "corrected_clock_out": "2025-07-28T17:00:00Z",
        "reason": "Incorrect clock-in time"
    }
    response = await test_client.post(
        "/api/v1/attendance-records/time-correction",
        json=correction_data,
        headers=auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Attendance record not found"

@pytest.mark.asyncio
async def test_get_time_corrections(test_client: AsyncClient, auth_headers: dict, attendance_record: AttendanceRecords, db_session: AsyncSession):
    correction = TimeCorrections(
        record_id=attendance_record.record_id,
        user_id=attendance_record.user_id,
        corrected_clock_in=datetime.now(timezone.utc),
        reason="Test correction",
        status="pending",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(correction)
    await db_session.commit()
    response = await test_client.get(
        "/api/v1/attendance-records/time-corrections",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["record_id"] == attendance_record.record_id

@pytest.mark.asyncio
async def test_approve_time_correction(test_client: AsyncClient, manager_auth_headers: dict, attendance_record: AttendanceRecords, db_session: AsyncSession):
    correction = TimeCorrections(
        record_id=attendance_record.record_id,
        user_id=attendance_record.user_id,
        corrected_clock_in=datetime.now(timezone.utc),
        reason="Test correction",
        status="pending",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(correction)
    await db_session.commit()
    await db_session.refresh(correction)
    response = await test_client.put(
        f"/api/v1/attendance-records/time-corrections/{correction.correction_id}",
        json="approved",
        headers=manager_auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["corrected_clock_in"] is not None

@pytest.mark.asyncio
async def test_approve_time_correction_unauthorized(test_client: AsyncClient, auth_headers: dict, attendance_record: AttendanceRecords, db_session: AsyncSession):
    correction = TimeCorrections(
        record_id=attendance_record.record_id,
        user_id=attendance_record.user_id,
        corrected_clock_in=datetime.now(timezone.utc),
        reason="Test correction",
        status="pending",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(correction)
    await db_session.commit()
    await db_session.refresh(correction)
    response = await test_client.put(
        f"/api/v1/attendance-records/time-corrections/{correction.correction_id}",
        json="approved",
        headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to approve/reject corrections"

@pytest.mark.asyncio
async def test_get_attendance_summary(test_client: AsyncClient, auth_headers: dict, attendance_record: AttendanceRecords, db_session: AsyncSession):
    attendance_record.clock_out_time = attendance_record.clock_in_time.replace(hour=17)
    db_session.add(attendance_record)
    await db_session.commit()
    response = await test_client.get(
        "/api/v1/attendance-records/summary",
        params={"start_date": date.today().replace(day=1), "end_date": date.today()},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == attendance_record.user_id
    assert data["total_hours"] > 0
    assert data["period_start"] == str(date.today().replace(day=1))
    assert data["period_end"] == str(date.today())

@pytest.mark.asyncio
async def test_export_attendance_csv(test_client: AsyncClient, auth_headers: dict, attendance_record: AttendanceRecords, db_session: AsyncSession):
    response = await test_client.get(
        "/api/v1/attendance-records/export/csv",
        params={"start_date": date.today().replace(day=1), "end_date": date.today()},
        headers=auth_headers
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert "attachment" in response.headers["content-disposition"]
    content = response.text
    assert "Record ID,Clock In,Clock Out,Created At,Updated At" in content
    assert str(attendance_record.record_id) in content

@pytest.mark.asyncio
async def test_export_attendance_pdf(test_client: AsyncClient, auth_headers: dict, attendance_record: AttendanceRecords, db_session: AsyncSession):
    response = await test_client.get(
        "/api/v1/attendance-records/export/pdf",
        params={"start_date": date.today().replace(day=1), "end_date": date.today()},
        headers=auth_headers
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]