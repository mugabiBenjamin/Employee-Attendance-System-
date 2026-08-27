from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.services.department_service import (
    create_department,
    get_department,
    list_departments,
    update_department,
    delete_department,
)
from app.schemas.department import (
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentOut,
)
from app.core.permissions import require_permissions_dependency
from app.core.enums import Permission


router = APIRouter(prefix="/departments", tags=["Departments"])


@router.post(
    "/",
    response_model=DepartmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_department_endpoint(
    department: DepartmentCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(
        require_permissions_dependency([Permission.CREATE_DEPARTMENT])
    ),
) -> DepartmentOut:
    request_id = getattr(request.state, "request_id", None)

    return await create_department(
        department,
        request,
        current_user,
        db,
        request_id,
    )


@router.get(
    "/{department_id}",
    response_model=DepartmentOut,
)
async def get_department_endpoint(
    department_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(
        require_permissions_dependency([Permission.VIEW_DEPARTMENT])
    ),
) -> DepartmentOut:
    request_id = getattr(request.state, "request_id", None)

    return await get_department(
        department_id,
        db,
        request_id,
    )


@router.get(
    "/",
    response_model=List[DepartmentOut],
)
async def list_departments_endpoint(
    request: Request,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _=Depends(
        require_permissions_dependency([Permission.VIEW_DEPARTMENT])
    ),
) -> List[DepartmentOut]:
    request_id = getattr(request.state, "request_id", None)

    return await list_departments(
        skip,
        limit,
        db,
        settings,
        request_id,
    )


@router.put(
    "/{department_id}",
    response_model=DepartmentOut,
)
async def update_department_endpoint(
    department_id: int,
    department_update: DepartmentUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(
        require_permissions_dependency([Permission.UPDATE_DEPARTMENT])
    ),
) -> DepartmentOut:
    request_id = getattr(request.state, "request_id", None)

    return await update_department(
        department_id,
        department_update,
        request,
        current_user,
        db,
        request_id,
    )


@router.delete(
    "/{department_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_department_endpoint(
    department_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(
        require_permissions_dependency([Permission.DELETE_DEPARTMENT])
    ),
) -> None:
    request_id = getattr(request.state, "request_id", None)

    await delete_department(
        department_id,
        request,
        current_user,
        db,
        request_id,
    )