from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime, timezone
from app.schemas.leave import (
    LeaveRequestCreate, LeaveRequestUpdate, LeaveRequestOut, 
    LeaveBalanceOut, LeavePolicyCreate, LeavePolicyUpdate, 
    LeavePolicyOut, LeaveApprovalWorkflowCreate, LeaveApprovalWorkflowOut, 
    HolidayCalendarCreate, HolidayCalendarUpdate, HolidayCalendarOut
)
from app.services.leave_service import (
    create_leave_request, update_leave_request, get_leave_request_by_id, 
    get_user_leave_requests, get_leave_balance, create_leave_approval_workflow, 
    get_holidays, validate_leave_policy, update_leave_balance
)
from app.services.holiday_service import (
    create_holiday, update_holiday, get_holiday_by_id, delete_holiday
)
from app.models.users import Users
from app.models.leave import LeavePolicy, LeaveRequest
from app.api.deps import get_db_session, get_current_active_user
from app.services.auth_service import check_user_permission
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

async def is_manager_or_hr(db: AsyncSession, user: Users) -> bool:
    from sqlmodel import select
    from app.models.user_roles import UserRoles
    from app.models.user_roles import Roles
    query = select(UserRoles).join(Roles).where(
        UserRoles.user_id == user.user_id,
        UserRoles.is_active == True,
        Roles.role_name.in_(["Manager", "HR", "Admin", "Super_Admin"])
    )
    result = await db.execute(query)
    return result.first() is not None

async def check_approval_level_permission(db: AsyncSession, user: Users, leave_id: int) -> bool:
    from sqlmodel import select
    query = select(LeavePolicy).join(LeaveRequest).where(
        LeaveRequest.leave_id == leave_id
    )
    result = await db.execute(query)
    policy = result.scalar_one_or_none()
    
    if not policy:
        return False
    
    required_level = policy.approval_levels
    has_permission = await check_user_permission(db, user.user_id, f"approve_leave_level_{required_level}")
    return has_permission or await is_manager_or_hr(db, user)

@router.post("/", 
    response_model=LeaveRequestOut, 
    status_code=status.HTTP_201_CREATED,
    summary="Create leave request",
    description="Create a new leave request with validated leave type and status"
)
async def create_new_leave_request(
    leave_request: LeaveRequestCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Create a new leave request."""
    valid_leave_types = ["annual", "sick", "maternity", "paternity", "emergency", "unpaid", 
                        "casual", "compensatory", "bereavement", "leave_of_absence", "public_holiday"]
    if leave_request.leave_type not in valid_leave_types:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                          detail=f"Invalid leave type. Must be one of {valid_leave_types}")
    
    valid_statuses = ["draft", "under_review", "completed"]
    if leave_request.status not in valid_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                          detail=f"Invalid status. Must be one of {valid_statuses}")
    
    if leave_request.user_id != current_user.user_id and not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to create leave request for this user")
    
    return await create_leave_request(db, leave_request, current_user)

@router.put("/{leave_id}", 
    response_model=LeaveRequestOut,
    summary="Update leave request",
    description="Update an existing leave request with validated status"
)
async def update_leave_request(
    leave_id: int,
    leave_update: LeaveRequestUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Update an existing leave request."""
    leave_request = await get_leave_request_by_id(db, leave_id, current_user)
    if not leave_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                          detail="Leave request not found")
    
    if leave_request.user_id != current_user.user_id and not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to update this leave request")
    
    if leave_update.status:
        valid_statuses = ["draft", "under_review", "cancelled", "completed"]
        if leave_update.status not in valid_statuses:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"Invalid status. Must be one of {valid_statuses}")
    
    return await update_leave_request(db, leave_id, leave_update, current_user)

@router.get("/{leave_id}", 
    response_model=LeaveRequestOut,
    summary="Get leave request",
    description="Retrieve specific leave request by ID"
)
async def get_leave_request(
    leave_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Get a specific leave request by its ID."""
    leave_request = await get_leave_request_by_id(db, leave_id, current_user)
    if not leave_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                          detail="Leave request not found")
    
    if leave_request.user_id != current_user.user_id and not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to view this leave request")
    
    return leave_request

@router.get("/user/{user_id}", 
    response_model=List[LeaveRequestOut],
    summary="Get leave request history",
    description="Retrieve leave request history for a user with optional date filtering"
)
async def get_leave_request_history(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Get leave request history for a specific user."""
    if user_id != current_user.user_id and not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to view this user's leave history")
    
    return await get_user_leave_requests(db, user_id, start_date, end_date, skip, limit)

@router.get("/balance/{user_id}", 
    response_model=List[LeaveBalanceOut],
    summary="Get leave balance",
    description="Retrieve leave balance for a user with optional year filtering"
)
async def get_user_leave_balance(
    user_id: int,
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Get leave balance for a specific user."""
    if user_id != current_user.user_id and not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to view this user's leave balance")
    
    return await get_leave_balance(db, user_id, year)

@router.post("/{leave_id}/approve", 
    response_model=LeaveRequestOut,
    summary="Approve leave request",
    description="Approve a leave request with multi-level approval check"
)
async def approve_leave_request(
    leave_id: int,
    comments: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Approve a leave request."""
    if not await check_approval_level_permission(db, current_user, leave_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to approve this leave request")
    
    leave_request = await get_leave_request_by_id(db, leave_id, current_user)
    if not leave_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                          detail="Leave request not found")
    
    leave_update = LeaveRequestUpdate.model_construct(status="approved", comments=comments)
    return await update_leave_request(db, leave_id, leave_update, current_user)

@router.post("/{leave_id}/reject", 
    response_model=LeaveRequestOut,
    summary="Reject leave request",
    description="Reject a leave request with multi-level approval check"
)
async def reject_leave_request(
    leave_id: int,
    comments: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Reject a leave request."""
    if not await check_approval_level_permission(db, current_user, leave_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to reject this leave request")
    
    leave_request = await get_leave_request_by_id(db, leave_id, current_user)
    if not leave_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                          detail="Leave request not found")
    
    leave_update = LeaveRequestUpdate.model_construct(status="rejected", comments=comments)
    return await update_leave_request(db, leave_id, leave_update, current_user)

@router.post("/approval-workflow", 
    response_model=LeaveApprovalWorkflowOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create leave approval workflow",
    description="Create a new leave approval workflow for multi-level approvals"
)
async def create_approval_workflow(
    workflow: LeaveApprovalWorkflowCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Create a new leave approval workflow."""
    if not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to create approval workflows")
    
    valid_statuses = ["under_review", "approved", "rejected", "cancelled", "completed"]
    if workflow.status not in valid_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                          detail=f"Invalid status. Must be one of {valid_statuses}")
    
    return await create_leave_approval_workflow(db, workflow, current_user)

@router.post("/policy", 
    response_model=LeavePolicyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create leave policy",
    description="Create a new leave policy"
)
async def create_leave_policy(
    policy: LeavePolicyCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Create a new leave policy."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_leave_policies")
    if not has_permission:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to create leave policies")
    
    valid_leave_types = ["annual", "sick", "maternity", "paternity", "emergency", "unpaid", 
                        "casual", "compensatory", "bereavement", "leave_of_absence", "public_holiday"]
    if policy.leave_type not in valid_leave_types:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                          detail=f"Invalid leave type. Must be one of {valid_leave_types}")
    
    if policy.approval_levels < 1 or policy.approval_levels > 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                          detail="Approval levels must be between 1 and 5")
    
    db_policy = LeavePolicy(**policy.model_dump())
    db.add(db_policy)
    await db.commit()
    await db.refresh(db_policy)
    
    logger.info(f"Leave policy created, policy_id {db_policy.policy_id}")
    return LeavePolicyOut.model_validate(db_policy)

@router.put("/policy/{policy_id}", 
    response_model=LeavePolicyOut,
    summary="Update leave policy",
    description="Update an existing leave policy"
)
async def update_leave_policy(
    policy_id: int,
    policy_update: LeavePolicyUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Update an existing leave policy."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_leave_policies")
    if not has_permission:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to update leave policies")
    
    from sqlmodel import select
    query = select(LeavePolicy).where(LeavePolicy.policy_id == policy_id)
    result = await db.execute(query)
    policy = result.scalar_one_or_none()
    
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                          detail="Leave policy not found")
    
    update_data = policy_update.model_dump(exclude_none=True)
    
    if "leave_type" in update_data:
        valid_leave_types = ["annual", "sick", "maternity", "paternity", "emergency", "unpaid", 
                           "casual", "compensatory", "bereavement", "leave_of_absence", "public_holiday"]
        if update_data["leave_type"] not in valid_leave_types:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"Invalid leave type. Must be one of {valid_leave_types}")
    
    if "approval_levels" in update_data:
        if update_data["approval_levels"] < 1 or update_data["approval_levels"] > 5:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="Approval levels must be between 1 and 5")
    
    for key, value in update_data.items():
        setattr(policy, key, value)
    
    policy.updated_at = datetime.now(timezone.utc)
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    
    logger.info(f"Leave policy updated, policy_id {policy_id}")
    return LeavePolicyOut.model_validate(policy)

@router.post("/holiday", 
    response_model=HolidayCalendarOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create holiday",
    description="Create a new holiday in the calendar"
)
async def create_holiday_calendar(
    holiday: HolidayCalendarCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Create a new holiday in the calendar."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_holidays")
    if not has_permission:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to create holidays")
    
    return await create_holiday(db, holiday, current_user)

@router.put("/holiday/{holiday_id}", 
    response_model=HolidayCalendarOut,
    summary="Update holiday",
    description="Update an existing holiday in the calendar"
)
async def update_holiday_calendar(
    holiday_id: int,
    holiday_update: HolidayCalendarUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Update an existing holiday in the calendar."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_holidays")
    if not has_permission:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to update holidays")
    
    return await update_holiday(db, holiday_id, holiday_update, current_user)

@router.get("/holiday/{holiday_id}", 
    response_model=HolidayCalendarOut,
    summary="Get holiday",
    description="Retrieve specific holiday by ID"
)
async def get_holiday(
    holiday_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Get a specific holiday by its ID."""
    holiday = await get_holiday_by_id(db, holiday_id, current_user)
    if not holiday:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                          detail="Holiday not found")
    
    return holiday

@router.delete("/holiday/{holiday_id}", 
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete holiday",
    description="Delete a holiday from the calendar"
)
async def delete_holiday_calendar(
    holiday_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: Users = Depends(get_current_active_user)
):
    """Delete a holiday from the calendar."""
    has_permission = await check_user_permission(db, current_user.user_id, "manage_holidays")
    if not has_permission:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                          detail="Not authorized to delete holidays")
    
    await delete_holiday(db, holiday_id, current_user)
    return None