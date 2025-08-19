from fastapi import APIRouter, Depends, status, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.department_service import (
    create_department,
    get_department,
    list_departments,
    update_department,
    delete_department
)
from app.schemas.department import DepartmentCreate, DepartmentUpdate, DepartmentOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/departments", tags=["Departments"])

@router.post(
    "/",
    response_model=DepartmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new department",
    description="Create a new department with provided details."
)
@require_permissions([Permission.CREATE_DEPARTMENT])
async def create_department_endpoint(
    department: DepartmentCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> DepartmentOut:
    """Create a new department."""
    try:
        request_id = getattr(request.state, "request_id", None)
        return await create_department(department, request, current_user, db, request_id)
    except HTTPException as e:
        logger.error(f"Error creating department: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating department: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/{department_id}",
    response_model=DepartmentOut,
    summary="Get department by ID",
    description="Retrieve a department by its ID."
)
@require_permissions([Permission.VIEW_DEPARTMENT])
async def get_department_endpoint(
    department_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> DepartmentOut:
    """Retrieve a department by ID."""
    try:
        request_id = getattr(request.state, "request_id", None)
        return await get_department(department_id, db, request_id)
    except HTTPException as e:
        logger.error(f"Error retrieving department {department_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving department {department_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/",
    response_model=List[DepartmentOut],
    summary="List all departments",
    description="Retrieve a list of active departments with pagination."
)
@require_permissions([Permission.VIEW_DEPARTMENT])
async def list_departments_endpoint(
    request: Request,
    skip: int = 0,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[DepartmentOut]:
    """List all active departments with pagination."""
    try:
        request_id = getattr(request.state, "request_id", None)
        return await list_departments(skip, limit, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error listing departments: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing departments: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{department_id}",
    response_model=DepartmentOut,
    summary="Update a department",
    description="Update an existing department with provided details."
)
@require_permissions([Permission.UPDATE_DEPARTMENT])
async def update_department_endpoint(
    department_id: int,
    department_update: DepartmentUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> DepartmentOut:
    """Update a department."""
    try:
        request_id = getattr(request.state, "request_id", None)
        return await update_department(department_id, department_update, request, current_user, db, request_id)
    except HTTPException as e:
        logger.error(f"Error updating department {department_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating department {department_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{department_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a department",
    description="Soft delete a department by its ID."
)
@require_permissions([Permission.DELETE_DEPARTMENT])
async def delete_department_endpoint(
    department_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> None:
    """Soft delete a department."""
    try:
        request_id = getattr(request.state, "request_id", None)
        await delete_department(department_id, request, current_user, db, request_id)
    except HTTPException as e:
        logger.error(f"Error deleting department {department_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting department {department_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")