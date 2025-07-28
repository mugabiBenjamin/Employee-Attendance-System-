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
from app.models.departments import Departments
from app.models.user_departments import UserDepartments
from app.models.system_logs import SystemLogs
from app.services.user_department_service import (
    create_user_department,
    get_user_department_by_id,
    get_user_departments,
    update_user_department,
    delete_user_department,
)
from app.core.config import settings
from app.core.enums import SystemAction
from pydantic import BaseModel, ConfigDict

# Mock schemas for testing
class UserDepartmentCreateInternal(BaseModel):
    user_id: int
    department_id: int
    is_primary: bool = False

    model_config = ConfigDict(from_attributes=True)

class UserDepartmentUpdateInternal(BaseModel):
    department_id: int | None = None
    is_primary: bool | None = None

    model_config = ConfigDict(from_attributes=True)

class UserDepartmentOut(BaseModel):
    user_department_id: int
    user_id: int
    department_id: int
    is_primary: bool
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

@pytest_asyncio.fixture
async def test_user_department(db_session: AsyncSession, test_user: Users, test_department: Departments):
    user_department = UserDepartments(
        user_id=test_user.user_id,
        department_id=test_department.department_id,
        is_primary=True,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(user_department)
    await db_session.commit()
    await db_session.refresh(user_department)
    return user_department

@pytest.mark.asyncio
async def test_create_user_department_success(db_session: AsyncSession, test_user: Users, test_department: Departments):
    user_department_data = UserDepartmentCreateInternal(
        user_id=test_user.user_id,
        department_id=test_department.department_id,
        is_primary=True
    )
    result = await create_user_department(db_session, user_department_data, test_user)
    assert result is not None
    assert result.user_id == test_user.user_id
    assert result.department_id == test_department.department_id
    assert result.is_primary is True
    assert result.created_at is not None
    # Verify system log
    query = select(SystemLogs).where(SystemLogs.record_id == result.user_department_id)
    log_result = await db_session.execute(query)
    log = log_result.scalar_one_or_none()
    assert log is not None
    assert log.action == SystemAction.ASSIGN_DEPARTMENT
    assert log.table_affected == "user_departments"

@pytest.mark.asyncio
async def test_create_user_department_invalid_user(db_session: AsyncSession, test_department: Departments, test_user: Users):
    user_department_data = UserDepartmentCreateInternal(
        user_id=999,
        department_id=test_department.department_id,
        is_primary=False
    )
    with pytest.raises(HTTPException) as exc:
        await create_user_department(db_session, user_department_data, test_user)
    assert exc.value.status_code == 404
    assert exc.value.detail == "User not found"

@pytest.mark.asyncio
async def test_create_user_department_invalid_department(db_session: AsyncSession, test_user: Users):
    user_department_data = UserDepartmentCreateInternal(
        user_id=test_user.user_id,
        department_id=999,
        is_primary=False
    )
    with pytest.raises(HTTPException) as exc:
        await create_user_department(db_session, user_department_data, test_user)
    assert exc.value.status_code == 404
    assert exc.value.detail == "Department not found"

@pytest.mark.asyncio
async def test_create_user_department_already_assigned(db_session: AsyncSession, test_user: Users, test_department: Departments, test_user_department: UserDepartments):
    user_department_data = UserDepartmentCreateInternal(
        user_id=test_user.user_id,
        department_id=test_department.department_id,
        is_primary=False
    )
    with pytest.raises(HTTPException) as exc:
        await create_user_department(db_session, user_department_data, test_user)
    assert exc.value.status_code == 400
    assert exc.value.detail == "User is already assigned to this department"

@pytest.mark.asyncio
async def test_create_user_department_primary_switch(db_session: AsyncSession, test_user: Users, test_department: Departments, test_user_department: UserDepartments):
    new_department = Departments(
        name="New Department",
        description="New Description",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(new_department)
    await db_session.commit()
    await db_session.refresh(new_department)

    user_department_data = UserDepartmentCreateInternal(
        user_id=test_user.user_id,
        department_id=new_department.department_id,
        is_primary=True
    )
    result = await create_user_department(db_session, user_department_data, test_user)
    assert result.is_primary is True
    # Verify previous primary is no longer primary
    query = select(UserDepartments).where(UserDepartments.user_department_id == test_user_department.user_department_id)
    result_prev = await db_session.execute(query)
    prev_user_department = result_prev.scalar_one_or_none()
    assert prev_user_department.is_primary is False

@pytest.mark.asyncio
async def test_create_user_department_internal_error(db_session: AsyncSession, test_user: Users, test_department: Departments):
    user_department_data = UserDepartmentCreateInternal(
        user_id=test_user.user_id,
        department_id=test_department.department_id,
        is_primary=False
    )
    with patch.object(db_session, "commit", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await create_user_department(db_session, user_department_data, test_user)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error creating user department assignment"

@pytest.mark.asyncio
async def test_get_user_department_by_id_success(db_session: AsyncSession, test_user_department: UserDepartments):
    result = await get_user_department_by_id(db_session, test_user_department.user_department_id)
    assert result is not None
    assert result.user_department_id == test_user_department.user_department_id
    assert result.user_id == test_user_department.user_id
    assert result.department_id == test_user_department.department_id
    assert result.is_primary == test_user_department.is_primary

@pytest.mark.asyncio
async def test_get_user_department_by_id_not_found(db_session: AsyncSession):
    result = await get_user_department_by_id(db_session, 999)
    assert result is None

@pytest.mark.asyncio
async def test_get_user_department_by_id_internal_error(db_session: AsyncSession):
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await get_user_department_by_id(db_session, 1)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error retrieving user department assignment"

@pytest.mark.asyncio
async def test_get_user_departments_success(db_session: AsyncSession, test_user: Users, test_user_department: UserDepartments):
    result = await get_user_departments(db_session, test_user.user_id, skip=0, limit=10)
    assert len(result) >= 1
    assert any(ud.user_department_id == test_user_department.user_department_id for ud in result)
    assert all(ud.user_id == test_user.user_id for ud in result)

@pytest.mark.asyncio
async def test_get_user_departments_invalid_user(db_session: AsyncSession):
    with pytest.raises(HTTPException) as exc:
        await get_user_departments(db_session, 999, skip=0, limit=10)
    assert exc.value.status_code == 404
    assert exc.value.detail == "User not found"

@pytest.mark.asyncio
async def test_get_user_departments_empty(db_session: AsyncSession, test_user: Users):
    result = await get_user_departments(db_session, test_user.user_id, skip=0, limit=10)
    assert len(result) == 0

@pytest.mark.asyncio
async def test_get_user_departments_internal_error(db_session: AsyncSession, test_user: Users):
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await get_user_departments(db_session, test_user.user_id, skip=0, limit=10)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error retrieving department assignments"

@pytest.mark.asyncio
async def test_update_user_department_success(db_session: AsyncSession, test_user: Users, test_user_department: UserDepartments, test_department: Departments):
    new_department = Departments(
        name="New Department",
        description="New Description",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(new_department)
    await db_session.commit()
    await db_session.refresh(new_department)

    update_data = UserDepartmentUpdateInternal(
        department_id=new_department.department_id,
        is_primary=True
    )
    result = await update_user_department(db_session, test_user_department.user_department_id, update_data, test_user)
    assert result is not None
    assert result.user_department_id == test_user_department.user_department_id
    assert result.department_id == new_department.department_id
    assert result.is_primary is True
    # Verify system log
    query = select(SystemLogs).where(SystemLogs.record_id == test_user_department.user_department_id, SystemLogs.action == SystemAction.UPDATE_DEPARTMENT_ASSIGNMENT)
    log_result = await db_session.execute(query)
    log = log_result.scalar_one_or_none()
    assert log is not None
    assert log.action == SystemAction.UPDATE_DEPARTMENT_ASSIGNMENT
    assert log.table_affected == "user_departments"

@pytest.mark.asyncio
async def test_update_user_department_invalid_department(db_session: AsyncSession, test_user: Users, test_user_department: UserDepartments):
    update_data = UserDepartmentUpdateInternal(
        department_id=999
    )
    with pytest.raises(HTTPException) as exc:
        await update_user_department(db_session, test_user_department.user_department_id, update_data, test_user)
    assert exc.value.status_code == 404
    assert exc.value.detail == "Department not found"

@pytest.mark.asyncio
async def test_update_user_department_already_assigned(db_session: AsyncSession, test_user: Users, test_department: Departments, test_user_department: UserDepartments):
    new_department = Departments(
        name="New Department",
        description="New Description",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(new_department)
    await db_session.commit()
    await db_session.refresh(new_department)

    other_assignment = UserDepartments(
        user_id=test_user.user_id,
        department_id=new_department.department_id,
        is_primary=False,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(other_assignment)
    await db_session.commit()

    update_data = UserDepartmentUpdateInternal(
        department_id=new_department.department_id
    )
    with pytest.raises(HTTPException) as exc:
        await update_user_department(db_session, test_user_department.user_department_id, update_data, test_user)
    assert exc.value.status_code == 400
    assert exc.value.detail == "User is already assigned to this department"

@pytest.mark.asyncio
async def test_update_user_department_primary_switch(db_session: AsyncSession, test_user: Users, test_department: Departments, test_user_department: UserDepartments):
    new_department = Departments(
        name="New Department",
        description="New Description",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(new_department)
    await db_session.commit()
    await db_session.refresh(new_department)

    other_assignment = UserDepartments(
        user_id=test_user.user_id,
        department_id=new_department.department_id,
        is_primary=False,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(other_assignment)
    await db_session.commit()
    await db_session.refresh(other_assignment)

    update_data = UserDepartmentUpdateInternal(
        is_primary=True
    )
    result = await update_user_department(db_session, other_assignment.user_department_id, update_data, test_user)
    assert result.is_primary is True
    # Verify previous primary is no longer primary
    query = select(UserDepartments).where(UserDepartments.user_department_id == test_user_department.user_department_id)
    result_prev = await db_session.execute(query)
    prev_user_department = result_prev.scalar_one_or_none()
    assert prev_user_department.is_primary is False

@pytest.mark.asyncio
async def test_update_user_department_not_found(db_session: AsyncSession, test_user: Users):
    update_data = UserDepartmentUpdateInternal(
        is_primary=True
    )
    with pytest.raises(HTTPException) as exc:
        await update_user_department(db_session, 999, update_data, test_user)
    assert exc.value.status_code == 404
    assert exc.value.detail == "User department assignment not found"

@pytest.mark.asyncio
async def test_update_user_department_internal_error(db_session: AsyncSession, test_user: Users, test_user_department: UserDepartments):
    update_data = UserDepartmentUpdateInternal(
        is_primary=True
    )
    with patch.object(db_session, "commit", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await update_user_department(db_session, test_user_department.user_department_id, update_data, test_user)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error updating user department assignment"

@pytest.mark.asyncio
async def test_delete_user_department_success(db_session: AsyncSession, test_user: Users, test_user_department: UserDepartments):
    await delete_user_department(db_session, test_user_department.user_department_id, test_user)
    query = select(UserDepartments).where(
        UserDepartments.user_department_id == test_user_department.user_department_id,
        UserDepartments.is_active == True
    )
    result = await db_session.execute(query)
    assert result.scalar_one_or_none() is None
    # Verify system log
    query = select(SystemLogs).where(
        SystemLogs.record_id == test_user_department.user_department_id,
        SystemLogs.action == SystemAction.DELETE_DEPARTMENT_ASSIGNMENT
    )
    log_result = await db_session.execute(query)
    log = log_result.scalar_one_or_none()
    assert log is not None
    assert log.action == SystemAction.DELETE_DEPARTMENT_ASSIGNMENT
    assert log.table_affected == "user_departments"

@pytest.mark.asyncio
async def test_delete_user_department_not_found(db_session: AsyncSession, test_user: Users):
    with pytest.raises(HTTPException) as exc:
        await delete_user_department(db_session, 999, test_user)
    assert exc.value.status_code == 404
    assert exc.value.detail == "User department assignment not found"

@pytest.mark.asyncio
async def test_delete_user_department_internal_error(db_session: AsyncSession, test_user: Users, test_user_department: UserDepartments):
    with patch.object(db_session, "commit", side_effect=Exception("Database error")):
        with pytest.raises(HTTPException) as exc:
            await delete_user_department(db_session, test_user_department.user_department_id, test_user)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Error deleting user department assignment"