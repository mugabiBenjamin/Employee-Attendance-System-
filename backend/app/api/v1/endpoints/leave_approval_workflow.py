from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.models.users import Users
from app.core.permissions import require_permissions
from app.core.security import get_current_active_user
from app.core.config import Settings, get_settings
from app.core.enums import Permission
from app.services.leave_approval_workflow_service import (
    define_workflow_steps,
    get_workflow_by_type
)
from app.schemas.leave_approval_workflow import WorkflowStepCreate, WorkflowStepOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leave-approval-workflow", tags=["Leave Approval Workflow"])

@router.post("/", 
             response_model=List[WorkflowStepOut], 
             status_code=status.HTTP_201_CREATED,
             summary="Define leave approval workflow steps",
             description="Define steps for a leave approval workflow with approver sequencing.")
@require_permissions([Permission.MANAGE_WORKFLOWS])
async def define_workflow_steps_endpoint(
    workflow_steps: List[WorkflowStepCreate],
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[WorkflowStepOut]:
    """
    Define leave approval workflow steps by delegating to leave_approval_workflow_service.
    """
    return await define_workflow_steps(workflow_steps, current_user, db, settings)

@router.get("/{leave_type}", 
            response_model=List[WorkflowStepOut],
            summary="Get workflow by leave type",
            description="Retrieve approval workflow steps for a specific leave type.")
@require_permissions([Permission.VIEW_WORKFLOWS])
async def get_workflow_by_type_endpoint(
    leave_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings)
) -> List[WorkflowStepOut]:
    """
    Retrieve workflow steps by leave type by delegating to leave_approval_workflow_service.
    """
    return await get_workflow_by_type(leave_type, current_user, db, settings)