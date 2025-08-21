from fastapi import APIRouter, Depends, status, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.core.config import Settings, get_settings
from app.core.exceptions import ValidationError
from app.services.employee_hierarchy_service import (
    create_employee_hierarchy,
    get_employee_hierarchy,
    list_employee_hierarchies,
    update_employee_hierarchy,
    delete_employee_hierarchy
)
from app.schemas.employee_hierarchy import (
    EmployeeHierarchyCreate,
    EmployeeHierarchyUpdate,
    EmployeeHierarchyOut
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employee-hierarchy", tags=["Employee Hierarchy"])

@router.post(
    "/",
    response_model=EmployeeHierarchyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create employee hierarchy",
    description="Create a new employee-manager relationship."
)
async def create_employee_hierarchy_endpoint(
    hierarchy: EmployeeHierarchyCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> EmployeeHierarchyOut:
    """Create a new employee-manager relationship.

    Args:
        hierarchy: The employee hierarchy data to create.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        EmployeeHierarchyOut: The created employee hierarchy.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await create_employee_hierarchy(hierarchy, request, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error creating employee hierarchy: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating employee hierarchy: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/{hierarchy_id}",
    response_model=EmployeeHierarchyOut,
    summary="Get employee hierarchy by ID",
    description="Retrieve an employee hierarchy by its ID."
)
async def get_employee_hierarchy_endpoint(
    hierarchy_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> EmployeeHierarchyOut:
    """Retrieve an employee hierarchy by ID.

    Args:
        hierarchy_id: The ID of the employee hierarchy to retrieve.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.

    Returns:
        EmployeeHierarchyOut: The retrieved employee hierarchy.

    Raises:
        HTTPException: For validation errors (422), not found (404), unauthorized (403), or server errors (500).
    """
    try:
        if hierarchy_id <= 0:
            raise ValidationError(detail="Invalid hierarchy ID")
        request_id = getattr(request.state, "request_id", None)
        return await get_employee_hierarchy(hierarchy_id, current_user, db, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error retrieving employee hierarchy {hierarchy_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving employee hierarchy {hierarchy_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.get(
    "/",
    response_model=List[EmployeeHierarchyOut],
    summary="List employee hierarchies",
    description="Retrieve a list of employee hierarchies, optionally filtered by employee_id, department_id, or supervisor_id with pagination."
)
async def list_employee_hierarchies_endpoint(
    employee_id: Optional[int] = None,
    department_id: Optional[int] = None,
    supervisor_id: Optional[int] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    request: Request = Depends(),
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> List[EmployeeHierarchyOut]:
    """List employee hierarchies with optional filters and pagination.

    Args:
        employee_id: Optional employee ID to filter hierarchies.
        department_id: Optional department ID to filter hierarchies.
        supervisor_id: Optional manager ID to filter hierarchies.
        skip: Number of records to skip for pagination (default: 0).
        limit: Maximum number of records to return (default: DEFAULT_PAGE_SIZE).
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        List[EmployeeHierarchyOut]: List of employee hierarchies.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        request_id = getattr(request.state, "request_id", None)
        return await list_employee_hierarchies(employee_id, department_id, supervisor_id, skip, limit, current_user, db, settings, request_id)
    except HTTPException as e:
        logger.error(f"Error listing employee hierarchies: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing employee hierarchies: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.put(
    "/{hierarchy_id}",
    response_model=EmployeeHierarchyOut,
    summary="Update employee hierarchy",
    description="Update an existing employee hierarchy."
)
async def update_employee_hierarchy_endpoint(
    hierarchy_id: int,
    hierarchy_update: EmployeeHierarchyUpdate,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> EmployeeHierarchyOut:
    """Update an employee hierarchy.

    Args:
        hierarchy_id: The ID of the employee hierarchy to update.
        hierarchy_update: The updated employee hierarchy data.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        EmployeeHierarchyOut: The updated employee hierarchy.

    Raises:
        HTTPException: For validation errors (422), not found (404), or server errors (500).
    """
    try:
        if hierarchy_id <= 0:
            raise ValidationError(detail="Invalid hierarchy ID")
        request_id = getattr(request.state, "request_id", None)
        return await update_employee_hierarchy(hierarchy_id, hierarchy_update, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error updating employee hierarchy {hierarchy_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating employee hierarchy {hierarchy_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")

@router.delete(
    "/{hierarchy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete employee hierarchy",
    description="Soft delete an employee hierarchy."
)
async def delete_employee_hierarchy_endpoint(
    hierarchy_id: int,
    request: Request,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> None:
    """Soft delete an employee hierarchy.

    Args:
        hierarchy_id: The ID of the employee hierarchy to delete.
        request: The incoming HTTP request for logging client details.
        current_user: The authenticated user performing the action.
        db: Database session dependency.
        settings: Application settings.

    Returns:
        None: No content returned on successful deletion.

    Raises:
        HTTPException: For validation errors (422), not found (404), business logic errors (422), or server errors (500).
    """
    try:
        if hierarchy_id <= 0:
            raise ValidationError(detail="Invalid hierarchy ID")
        request_id = getattr(request.state, "request_id", None)
        await delete_employee_hierarchy(hierarchy_id, request, current_user, db, settings, request_id)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except HTTPException as e:
        logger.error(f"Error deleting employee hierarchy {hierarchy_id}: {str(e)}", extra={"request_id": request_id})
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting employee hierarchy {hierarchy_id}: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")